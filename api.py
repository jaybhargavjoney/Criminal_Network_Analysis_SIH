from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import GraphDatabase

app = FastAPI()

# Allow frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "admin123"  # Update with your Neo4j password
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

@app.get("/api/network-stats")
def get_network_stats():
    with driver.session() as session:
        query = """
        MATCH (n)
        OPTIONAL MATCH (n)-[:COMMUNICATED|TRANSFERRED]-(m)
        RETURN n.number AS phone, n.account_id AS account, count(m) AS connections
        ORDER BY connections DESC
        LIMIT 10
        """
        result = session.run(query)
        nodes = []
        for record in result:
            identifier = record["phone"] if record["phone"] else record["account"]
            if identifier:
                nodes.append({
                    "id": identifier,
                    "connections": record["connections"]
                })
        return {"suspects": nodes}