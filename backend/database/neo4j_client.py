import logging
import re
import time
from typing import Any
from neo4j import GraphDatabase

from backend.auth.firebase_auth import AuthUser
from backend.core.config import settings

logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self):
        self.uri = settings.NEO4J_URI
        self.username = settings.NEO4J_USERNAME
        self.password = settings.NEO4J_PASSWORD
        self.driver = None
        self._last_verified = 0.0
        self._connect()

    def _connect(self):
        """Internal helper to establish or reset the driver. Non-blocking & Safe."""
        if not (self.uri and self.username and self.password):
            logger.warning("Neo4j configuration missing. Database functionality will be disabled.")
            return

        try:
            if self.driver:
                try:
                    self.driver.close()
                except:
                    pass
            
            logger.info(f"Attempting Neo4j connection to {self.uri} (Timeout: 5s)...")
            self.driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.username, self.password),
                connection_timeout=5.0
            )
            # Connectivity check
            self.driver.verify_connectivity()
            self._last_verified = time.time()
            logger.info("Connected to Neo4j Graph Database successfully.")
        except Exception as e:
            # DO NOT re-raise. We want the app to stay alive.
            logger.error(f"FATAL: Database connection failed (DNS/Network). App will start in OFFLINE mode: {e}")
            self.driver = None 

    def _ensure_connection(self):
        """Lazy connectivity check (at most once per 60s)."""
        if not self.driver:
            self._connect()
            return

        # Skip if verified recently
        if time.time() - self._last_verified < 60.0:
            return

        try:
            self.driver.verify_connectivity()
            self._last_verified = time.time()
        except Exception as e:
            logger.warning(f"Neo4j connection defunct, attempting reset: {e}")
            self._connect()

    def close(self):
        if self.driver is not None:
            self.driver.close()

    def get_user_profile(self, auth_user: AuthUser) -> dict[str, Any]:
        """Fetch or create user profile."""
        if auth_user.role_hint == "student" and auth_user.reg_no_hint:
            return {
                "uid": auth_user.uid,
                "role": "student",
                "reg_no": auth_user.reg_no_hint,
                "email": auth_user.email,
            }

        if auth_user.role_hint in {"faculty", "hod"} and auth_user.faculty_id_hint:
            return {
                "uid": auth_user.uid,
                "role": auth_user.role_hint,
                "faculty_id": auth_user.faculty_id_hint,
                "email": auth_user.email,
            }

        if not self.driver:
            return {"role": auth_user.role_hint or "student", "uid": auth_user.uid}
            
        uid = auth_user.uid
        email = auth_user.email or ""
        
        self._ensure_connection()
        query = """
        MERGE (u:User {uid: $uid})
        ON CREATE SET u.email = $email, u.role = $role, u.name = $name
        ON MATCH SET u.name = CASE WHEN u.name IS NULL THEN $name ELSE u.name END
        RETURN u.role AS role, u.reg_no AS reg_no, u.name AS name
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, uid=uid, email=email, name=auth_user.display_name, role=auth_user.role_hint or "student")
                record = result.single()
                
                profile = {
                    "role": record["role"] if record else (auth_user.role_hint or "student"), 
                    "uid": uid,
                    "name": record["name"] if record else auth_user.display_name
                }
                
                # If they have a linked Student record (via reg_no string on User or link)
                if record and record["reg_no"]:
                    profile["reg_no"] = record["reg_no"]
                else:
                    # Optional: link student by email if it exists
                    link_q = "MATCH (s:Student {email: $email}) MERGE (u:User {uid: $uid})-[:IS_STUDENT]->(s) SET u.reg_no = s.reg_no RETURN s.reg_no AS reg_no"
                    link_res = session.run(link_q, email=email, uid=uid).single()
                    if link_res:
                        profile["reg_no"] = link_res["reg_no"]
                        
                return profile
        except Exception as e:
            logger.error(f"Neo4j profile fetch error: {e}")
            return {"role": "student", "uid": uid}


    def _looks_like_reg_no(self, query: str) -> bool:
        """Heuristic: registration numbers contain digits and letters (e.g. 23091A3349)."""
        q = query.strip().upper()
        # Reg no pattern: starts with digits, contains a letter section
        return bool(q) and any(c.isdigit() for c in q) and any(c.isalpha() for c in q)

    def _clean_lookup_text(self, query: str) -> str:
        q = str(query or "").strip()
        q = re.sub(r"\s+", " ", q)
        return q

    def find_student_by_query(self, query_str: str) -> list[dict[str, Any]]:
        """Search students by registration number or name. Returns all matches."""
        self._ensure_connection()
        if not self.driver or not query_str:
            return []

        q = self._clean_lookup_text(query_str)
        if self._looks_like_reg_no(q):
            # Exact reg_no match
            neo_query = "MATCH (s:Student {reg_no: $reg_no}) RETURN s { .reg_no, .name, .email, .gender, .cgpa, .backlogs, .category, .updated_at } AS data"
            try:
                with self.driver.session() as session:
                    record = session.run(neo_query, reg_no=q.upper()).single()
                    return [record["data"]] if record else []
            except Exception as e:
                logger.error(f"Neo4j reg_no search error: {e}")
                return []
        else:
            # Name search with ranking:
            # 1) exact full-name match
            # 2) startswith match
            # 3) contains match
            # This makes partial asks like "sridhar" reliably find "Mukkandi Sridhar".
            neo_query = """
            MATCH (s:Student)
            WITH s, toLower(coalesce(s.name, '')) AS lname, toLower($name) AS q
            WHERE lname CONTAINS q
            WITH s, lname, q,
              CASE
                WHEN lname = q THEN 0
                WHEN lname STARTS WITH q THEN 1
                WHEN ANY(tok IN split(lname, ' ') WHERE tok STARTS WITH q) THEN 2
                ELSE 3
              END AS rank_score
            RETURN s { .reg_no, .name, .email, .gender, .cgpa, .backlogs, .category, .updated_at } AS data
            ORDER BY rank_score ASC, toLower(s.name) ASC
            LIMIT 10
            """
            try:
                with self.driver.session() as session:
                    results = session.run(neo_query, name=q)
                    records = [r["data"] for r in results]
                    if records:
                        return records

                    # Fallback: tokenized broad match for noisy inputs.
                    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", q.lower()) if len(t) >= 3]
                    if not tokens:
                        return []
                    fallback_q = """
                    MATCH (s:Student)
                    WITH s, toLower(coalesce(s.name, '')) AS lname, $tokens AS toks
                    WHERE ANY(t IN toks WHERE lname CONTAINS t)
                    RETURN s { .reg_no, .name, .email, .gender, .cgpa, .backlogs, .category, .updated_at } AS data
                    ORDER BY toLower(s.name) ASC
                    LIMIT 10
                    """
                    fallback_results = session.run(fallback_q, tokens=tokens)
                    return [r["data"] for r in fallback_results]
            except Exception as e:
                logger.error(f"Neo4j name search error: {e}")
                return []

    def get_student_data(self, reg_no: str) -> dict[str, Any] | None:
        """Fetch a specific student by Registration Number including Program."""
        self._ensure_connection()
        if not self.driver or not reg_no:
            return None
        query = """
        MATCH (s:Student {reg_no: $reg_no})
        OPTIONAL MATCH (s)-[:ENROLLED_IN]->(p:Program)
        RETURN s { .*, program: p.name } AS data
        """
        try:
            with self.driver.session() as session:
                record = session.run(query, reg_no=reg_no.upper()).single()
                return record["data"] if record else None
        except Exception as e:
            logger.error(f"Neo4j get student error: {e}")
            return None


    def list_all_students(self) -> list[dict[str, Any]]:
        """Used by HOD dashboard. Returns core fields + program."""
        self._ensure_connection()
        if not self.driver:
            return []
        query = """
        MATCH (s:Student)
        OPTIONAL MATCH (s)-[:ENROLLED_IN]->(p:Program)
        RETURN s { .*, program: p.name } AS data 
        ORDER BY s.reg_no
        """
        try:
            with self.driver.session() as session:
                results = session.run(query)
                return [record["data"] for record in results]
        except Exception as e:
            logger.error(f"Neo4j list students error: {e}")
            return []


    def update_student_data(self, reg_no: str, fields: dict[str, Any]) -> bool:
        """Update core student fields and program relationship."""
        self._ensure_connection()
        if not self.driver or not reg_no or not fields:
            return False

        fields = self._coerce_student_numeric_fields(fields)
        reg_no = reg_no.upper()
        program = fields.pop("program", None)

        query = """
        MATCH (s:Student {reg_no: $reg_no})
        SET s += $fields, s.updated_at = datetime()
        WITH s
        WHERE $program IS NOT NULL
        MATCH (s)-[old:ENROLLED_IN]->(:Program) DELETE old
        WITH s
        MERGE (p:Program {name: $program})
        MERGE (s)-[:ENROLLED_IN]->(p)
        RETURN s
        """
        # If program is not provided, we just update fields
        simple_query = "MATCH (s:Student {reg_no: $reg_no}) SET s += $fields, s.updated_at = datetime() RETURN s"
        
        try:
            with self.driver.session() as session:
                if program:
                    result = session.run(query, reg_no=reg_no, fields=fields, program=program)
                else:
                    result = session.run(simple_query, reg_no=reg_no, fields=fields)
                return result.single() is not None
        except Exception as e:
            logger.error(f"Neo4j update student error: {e}")
            return False


    def add_student(self, data: dict[str, Any]) -> bool:
        """Add student with core academic fields and program relationship."""
        self._ensure_connection()
        if not self.driver or "reg_no" not in data:
            return False

        data = self._coerce_student_numeric_fields(data)
        reg_no = data.get("reg_no", "").upper()
        program = data.pop("program", "General")

        query = """
        MERGE (s:Student {reg_no: $reg_no})
        SET s.name = $data.name,
            s.email = $data.email,
            s.gender = $data.gender,
            s.cgpa = $data.cgpa,
            s.backlogs = $data.backlogs,
            s.category = $data.category,
            s.updated_at = datetime()
        WITH s
        MERGE (p:Program {name: $program})
        MERGE (s)-[:ENROLLED_IN]->(p)
        RETURN s
        """
        try:
            with self.driver.session() as session:
                session.run(query, reg_no=reg_no, data=data, program=program)
                return True
        except Exception as e:
            logger.error(f"Neo4j add student error: {e}")
            return False

    def add_attendance(self, reg_no: str, month: str, year: int, percentage: float, classes_held: int, classes_attended: int):
        """[STUB] Add monthly attendance record for a student."""
        pass


    def remove_student(self, reg_no: str) -> bool:
        """HOD tool to remove a student."""
        self._ensure_connection()
        if not self.driver or not reg_no:
            return False
            
        query = "MATCH (s:Student {reg_no: $reg_no}) DETACH DELETE s"
        try:
            with self.driver.session() as session:
                session.run(query, reg_no=reg_no.upper())
                return True
        except Exception as e:
            logger.error(f"Neo4j remove student error: {e}")
            return False

    def query_students(self, cypher: str) -> dict[str, Any]:
        """Executes a read-only Cypher query with security checks."""
        self._ensure_connection()
        if not self.driver:
            return {"error": "Database not connected", "suggestion": "fallback"}

        whitelist = {"MATCH", "WHERE", "RETURN", "WITH", "ORDER", "BY", "LIMIT", "UNWIND", "COUNT", "AS"}
        blacklist = {"CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP", "CALL", "INDEX", "CONSTRAINT"}

        upper_q = (cypher or "").upper()
        keywords = set(re.findall(r"\b[A-Z_]+\b", upper_q))
        
        # 1. Security Check (Blacklist)
        blocked = sorted(word for word in blacklist if word in keywords)
        if blocked:
            return {
                "error": f"Security Violation: '{blocked[0]}' is not allowed in search queries.",
                "suggestion": "fallback",
            }
        
        # 2. Logic Check (Keywords)
        allowed = keywords.intersection(whitelist)

        # 3. Schema Check (Property Existence)
        lower_cypher = (cypher or "").lower()
        invalid_props = ["s.department", "s.program", "s.branch"]
        for prop in invalid_props:
            if prop in lower_cypher:
                return {
                    "error": f"{prop} does not exist. Use ENROLLED_IN relationship to Program node instead.",
                    "suggestion": "retry"
                }

        if "RETURN" not in allowed:
            return {"error": "Search query must include RETURN clause.", "suggestion": "retry"}

        # 2. Execution
        try:
            with self.driver.session() as session:
                # Use execute_read for safety
                def _tx(tx):
                    result = tx.run(cypher)
                    return [record.data() for record in result]
                
                results = session.execute_read(_tx)
                # Flatten the data() return if it's just 's' or similar
                flattened = []
                for res in results:
                    # If result is like {'s': {...props}}, extract props
                    if len(res) == 1 and isinstance(list(res.values())[0], dict):
                        flattened.append(list(res.values())[0])
                    else:
                        # Normalize projected keys like "s.name" -> "name"
                        normalized_row = {}
                        for key, value in res.items():
                            normalized_key = str(key).split(".")[-1]
                            normalized_row[normalized_key] = value
                        flattened.append(normalized_row)

                return {"data": flattened, "error": None}
        except Exception as e:
            logger.error(f"Cypher Query Failed: {e}")
            return {"error": str(e), "suggestion": "retry"}

    def get_student_schema(self) -> dict[str, Any]:
        """Return dynamic student property schema inferred from graph data."""
        self._ensure_connection()
        if not self.driver:
            return {"properties": [], "error": "Database not connected"}

        query = """
        MATCH (s:Student)
        WITH s LIMIT 50
        UNWIND keys(s) AS key
        WITH key, collect(s[key]) AS vals
        WITH key, [v IN vals WHERE v IS NOT NULL | v][0] AS sample
        RETURN key AS field, sample
        ORDER BY field
        """
        try:
            with self.driver.session() as session:
                rows = session.run(query)
                properties = []
                for row in rows:
                    field = row.get("field")
                    sample = row.get("sample")
                    if not field:
                        continue
                    dtype = type(sample).__name__ if sample is not None else "unknown"
                    properties.append({"field": field, "type": dtype})
                return {"properties": properties, "error": None}
        except Exception as e:
            logger.error(f"get_student_schema failed: {e}")
            return {"properties": [], "error": str(e)}

    def _coerce_student_numeric_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize known numeric student fields before writing to Neo4j."""
        normalized = dict(payload or {})
        numeric_fields: dict[str, type] = {
            "cgpa": float,
            "backlogs": int,
        }
        for field, caster in numeric_fields.items():
            if field not in normalized:
                continue
            try:
                value = normalized[field]
                if caster is int:
                    normalized[field] = int(float(value))
                else:
                    normalized[field] = float(value)
            except (TypeError, ValueError):
                # Keep original value if coercion fails; upstream validation may reject it.
                pass
        return normalized

    def fix_data_types(self) -> dict[str, int | str]:
        """Idempotent migration that casts numeric-like string properties to numeric types."""
        self._ensure_connection()
        if not self.driver:
            return {"updated": 0}

        query = """
        MATCH (s:Student)
        WITH s,
             CASE
               WHEN s.cgpa IS NOT NULL AND toString(s.cgpa) =~ '^-?\\d+(\\.\\d+)?$'
               THEN toFloat(s.cgpa)
               ELSE s.cgpa
             END AS cgpa_val,
             CASE
               WHEN s.backlogs IS NOT NULL AND toString(s.backlogs) =~ '^-?\\d+(\\.\\d+)?$'
               THEN toInteger(toFloat(s.backlogs))
               ELSE s.backlogs
             END AS backlogs_val
        SET s.cgpa = cgpa_val,
            s.backlogs = backlogs_val
        RETURN count(s) AS updated
        """
        try:
            with self.driver.session() as session:
                result = session.execute_write(lambda tx: tx.run(query).single())
                return {"updated": int(result["updated"]) if result and result["updated"] is not None else 0}
        except Exception as e:
            logger.error(f"fix_data_types failed: {e}")
            return {"error": str(e)}


    def log_chat(self, entry: dict[str, Any]) -> None:
        """Write chat history to Graph DB."""
        if not self.driver:
            return
            
        query = """
        MERGE (u:User {uid: $uid})
        CREATE (l:ChatLog {
            message: $message,
            intent: $intent,
            started_at: $started_at,
            duration_ms: $duration_ms,
            error: $error
        })
        CREATE (u)-[:MADE_QUERY]->(l)
        """
        try:
            with self.driver.session() as session:
                session.run(
                    query, 
                    uid=entry.get("uid", "anonymous"),
                    message=entry.get("message", ""),
                    intent=entry.get("intent", "unknown"),
                    started_at=entry.get("started_at", 0.0),
                    duration_ms=entry.get("duration_ms", 0.0),
                    error=entry.get("error", "")
                )
        except Exception as e:
            pass # Logs must silently fail

    # --- Session Management (Delegated to Firestore) ---

    def get_chat_sessions(self, uid: str) -> list[dict[str, Any]]:
        from backend.database.firestore import db_client as fs_db
        return fs_db.get_chat_sessions(uid)

    def get_chat_session_history(self, uid: str, session_id: str) -> list[dict[str, Any]]:
        from backend.database.firestore import db_client as fs_db
        return fs_db.get_chat_session_history(uid, session_id)

    def save_chat_turn(self, uid: str, session_id: str, message: str, answer: str, intent: str = None, tool_used: str = None) -> None:
        from backend.database.firestore import db_client as fs_db
        return fs_db.save_chat_turn(uid, session_id, message, answer, intent, tool_used)

# Singleton instance
db_client = Neo4jClient()
