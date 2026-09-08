from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "janey7749" # Replace with your Neo4j password

def run_analytics(tx):
    query = """
    MATCH (n)
    OPTIONAL MATCH (n)-[:COMMUNICATED|TRANSFERRED]-(m)
    RETURN n.number AS phone, n.account_id AS account, count(m) AS connections
    ORDER BY connections DESC
    LIMIT 5
    """
    result = tx.run(query)
    print("Top Key Suspects & Hubs:")
    for record in result:
        identifier = record["phone"] if record["phone"] else record["account"]
        print(f"- Entity: {identifier} | Connections: {record['connections']}")

def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        session.execute_write(run_analytics)
    driver.close()

if __name__ == "__main__":
    main()