// migrate_schema.cypher

// 1. Create ENROLLED_IN from flat program property
MATCH (s:Student)
WHERE s.program IS NOT NULL
MERGE (p:Program {name: s.program})
MERGE (s)-[:ENROLLED_IN]->(p);

// 2. Drop everything unnecessary
MATCH (s:Student)
REMOVE s.strengths, 
       s.weaknesses, 
       s.performance,
       s.risk, 
       s.placement, 
       s.certifications,
       s.program, 
       s.activities;

// 3. Add updated_at
MATCH (s:Student)
SET s.updated_at = datetime();

// 4. Verification Check
MATCH (s:Student)-[:ENROLLED_IN]->(p:Program)
RETURN count(s) AS linked_students, p.name AS program;
