import logging
import time
from typing import Any
from neo4j import GraphDatabase

from backend.auth.firebase_auth import AuthUser, verify_firebase_token
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
        """Internal helper to establish or reset the driver."""
        if self.uri and self.username and self.password:
            try:
                if self.driver:
                    try:
                        self.driver.close()
                    except:
                        pass
                self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
                self.driver.verify_connectivity()
                self._last_verified = time.time()
                logger.info("Connected to Neo4j Graph Database successfully.")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")

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
        if not self.driver:
            return {"role": "student", "uid": auth_user.uid}
            
        uid = auth_user.uid
        email = auth_user.email or ""
        
        assigned_role = "student"
        if email in ["hod@department.edu", "faculty@department.edu"]:
            assigned_role = "faculty"
            
        self._ensure_connection()
        query = """
        MERGE (u:User {uid: $uid})
        ON CREATE SET u.email = $email, u.role = $assigned_role
        RETURN u.role AS role, u.reg_no AS reg_no
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, uid=uid, email=email, assigned_role=assigned_role)
                record = result.single()
                
                profile = {"role": record["role"] if record else assigned_role, "uid": uid}
                
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


    def get_student_data(self, reg_no: str) -> dict[str, Any] | None:
        """Fetch a specific student by Registration Number."""
        self._ensure_connection()
        if not self.driver or not reg_no:
            return None
        query = "MATCH (s:Student {reg_no: $reg_no}) RETURN properties(s) AS data"
        try:
            with self.driver.session() as session:
                record = session.run(query, reg_no=reg_no.upper()).single()
                return record["data"] if record else None
        except Exception as e:
            logger.error(f"Neo4j get student error: {e}")
            return None


    def list_all_students(self) -> list[dict[str, Any]]:
        """Used by HOD dashboard."""
        self._ensure_connection()
        if not self.driver:
            return []
        query = "MATCH (s:Student) RETURN properties(s) AS data ORDER BY s.reg_no"
        try:
            with self.driver.session() as session:
                results = session.run(query)
                return [record["data"] for record in results]
        except Exception as e:
            logger.error(f"Neo4j list students error: {e}")
            return []


    def update_student_data(self, reg_no: str, fields: dict[str, Any]) -> bool:
        """HOD tool to override fields."""
        self._ensure_connection()
        if not self.driver or not reg_no or not fields:
            return False
        
        # Cypher set properties via += operator
        query = """
        MATCH (s:Student {reg_no: $reg_no})
        SET s += $fields
        RETURN s
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, reg_no=reg_no.upper(), fields=fields)
                return result.single() is not None
        except Exception as e:
            logger.error(f"Neo4j update student error: {e}")
            return False


    def add_student(self, data: dict[str, Any]) -> bool:
        """HOD tool to add a student."""
        self._ensure_connection()
        if not self.driver or "reg_no" not in data:
            return False
            
        data["reg_no"] = data["reg_no"].upper()
        query = "MERGE (s:Student {reg_no: $reg_no}) SET s += $data RETURN s"
        try:
            with self.driver.session() as session:
                session.run(query, reg_no=data["reg_no"], data=data)
                return True
        except Exception as e:
            logger.error(f"Neo4j add student error: {e}")
            return False


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

# Singleton instance
db_client = Neo4jClient()
