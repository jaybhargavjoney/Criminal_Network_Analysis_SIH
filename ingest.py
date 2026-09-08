import pandas as pd
from neo4j import GraphDatabase

# Neo4j Database Connection Credentials
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "janey7749" # Replace with your Neo4j password

def ingest_cdrs(tx, csv_path):
    df = pd.read_csv(csv_path)
    for _, row in df.iterrows():
        tx.run("""
            MERGE (c1:Phone {number: $caller})
            MERGE (c2:Phone {number: $receiver})
            CREATE (c1)-[:COMMUNICATED {timestamp: $timestamp, duration: $duration}]->(c2)
        """, caller=row['caller'], receiver=row['receiver'], 
             timestamp=str(row['timestamp']), duration=int(row['duration']))

def ingest_transactions(tx, csv_path):
    df = pd.read_csv(csv_path)
    for _, row in df.iterrows():
        tx.run("""
            MERGE (a1:BankAccount {account_id: $sender})
            MERGE (a2:BankAccount {account_id: $receiver})
            CREATE (a1)-[:TRANSFERRED {amount: $amount, timestamp: $timestamp}]->(a2)
        """, sender=row['sender_acc'], receiver=row['receiver_acc'], 
             amount=float(row['amount']), timestamp=str(row['timestamp']))

def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    
    print("Ingesting Call Detail Records (CDRs)...")
    with driver.session() as session:
        session.execute_write(ingest_cdrs, "data/cdrs.csv")
        
    print("Ingesting Financial Transactions...")
    with driver.session() as session:
        session.execute_write(ingest_transactions, "data/transactions.csv")
        
    print("Multi-source data successfully mapped into Neo4j graph!")
    driver.close()

if __name__ == "__main__":
    main()