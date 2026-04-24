import sys, csv, os
sys.path.append(os.path.abspath('.'))

import firebase_admin
from firebase_admin import credentials, auth
from backend.core.config import settings
from backend.database.neo4j_client import db_client

# 1. Initialize Firebase
try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(settings.firebase_service_account_path)
    firebase_admin.initialize_app(cred)

PASSWORD = "15082006"

def create_user(email, password):
    try:
        user = auth.create_user(email=email, password=password)
        print(f"Created: {email}")
        return user.uid
    except Exception as e:
        if "EMAIL_EXISTS" in str(e):
            print(f"Exists: {email}")
            user = auth.get_user_by_email(email)
            # Update password to be sure
            auth.update_user(user.uid, password=password)
            return user.uid
        else:
            print(f"Error creating {email}: {e}")
            return None

print("Provisioning unified faculty...")
create_user("faculty@rgmcet.edu.in", "CSEAIML")

print("\nProcessing students from CSV...")
with open('students_data_new.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        reg_no = row.get("reg_no").strip()
        email = f"{reg_no}@rgmcet.edu.in".lower()
        password = reg_no.lower()
        uid = create_user(email, password)
        
        # Link user in Neo4j!
        if uid:
            with db_client.driver.session() as session:
                session.run("MERGE (u:User {uid: $uid}) SET u.email = $email, u.role = 'student', u.reg_no = $reg_no", 
                            uid=uid, email=email, reg_no=reg_no)

print("Provisioning Complete.")
