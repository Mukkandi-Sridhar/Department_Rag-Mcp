import os
from neo4j import GraphDatabase

URI = "neo4j+s://2a6d0c49.databases.neo4j.io"
AUTH = ("2a6d0c49", "yGWKbfQUVa6G89GeycqCMj5L0s_ghBaSiqeRCt5nNaw")

def test_connection():
    try:
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            driver.verify_connectivity()
            print("Connection successful with 2a6d0c49!")
    except Exception as e:
        print(f"Connection failed: {e}")
        try:
            with GraphDatabase.driver(URI, auth=("neo4j", "yGWKbfQUVa6G89GeycqCMj5L0s_ghBaSiqeRCt5nNaw")) as driver:
                driver.verify_connectivity()
                print("Connection successful with neo4j!")
        except Exception as e2:
            print(f"Connection failed second try: {e2}")

if __name__ == "__main__":
    test_connection()
