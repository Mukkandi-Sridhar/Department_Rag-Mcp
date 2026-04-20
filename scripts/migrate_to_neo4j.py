import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import csv
from backend.database.neo4j_client import db_client

def migrate():
    csv_file = os.path.join(os.path.dirname(__file__), '..', 'students_data_new.csv')
    if not os.path.exists(csv_file):
        print(f"File not found: {csv_file}")
        return
        
    count = 0
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            db_client.add_student(row)
            count += 1
            
    print(f"Successfully migrated {count} students into Neo4j Graph Database!")
    
if __name__ == "__main__":
    migrate()
