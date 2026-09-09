import os
import shutil
import pandas as pd
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from neo4j import GraphDatabase

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATABASE SETUP ---
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "janey7749"
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

# --- AUTOMATED MULTI-CRIME SCENARIO SEEDER ---
@app.on_event("startup")
def seed_crime_network():
    with driver.session() as session:
        session.run("""
            MERGE (case101:Case {case_id: "Case 101 - Hawala Extortion"})
            MERGE (case204:Case {case_id: "Case 204 - Cross-Border Smuggling"})
            
            MERGE (p1:Person {name: "Anita Rao"})
            MERGE (p2:Person {name: "Sunil Verma"})
            MERGE (p3:Person {name: "Rajesh Kumar"})
            
            MERGE (ph1:Phone {number: "+91-9876543210"})
            MERGE (ph2:Phone {number: "+91-9988776655"})
            MERGE (ph3:Phone {number: "+91-4123456789"})
            
            MERGE (a1:BankAccount {account_id: "ACC_001"})
            MERGE (a2:BankAccount {account_id: "ACC_002"})
            
            // Rajesh Kumar bridges multiple distinct crimes!
            MERGE (p1)-[:INVOLVED_IN]->(case101)
            MERGE (p2)-[:INVOLVED_IN]->(case101)
            MERGE (p3)-[:INVOLVED_IN]->(case101)
            MERGE (p3)-[:INVOLVED_IN]->(case204)
            
            MERGE (p1)-[:USES_PHONE]->(ph1)
            MERGE (p2)-[:USES_PHONE]->(ph2)
            MERGE (p3)-[:USES_PHONE]->(ph3)
            
            MERGE (ph1)-[:COMMUNICATED {timestamp: "2026-04-10 14:30:00", duration: 120}]->(ph2)
            MERGE (ph2)-[:COMMUNICATED {timestamp: "2026-04-10 15:00:00", duration: 300}]->(ph3)
            
            MERGE (a1)-[:TRANSFERRED {amount: 50000.0, timestamp: "2026-04-10 16:00:00"}]->(a2)
        """)

# --- SECURITY SETTINGS ---
SECRET_KEY = "super-secret-police-key"  
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

OFFICER_DB = {
    "badge123": {
        "username": "badge123",
        "password": "securepassword",
        "name": "Lead Investigator"
    }
}

@app.post("/api/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = OFFICER_DB.get(form_data.username)
    if not user or user["password"] != form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect badge number or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user["username"], "exp": expire}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return {"access_token": encoded_jwt, "token_type": "bearer"}

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid security token")
        return username
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired security token")

@app.get("/api/network-stats")
def get_network_stats(current_user: str = Depends(get_current_user)):
    with driver.session() as session:
        query = """
        MATCH (n)
        OPTIONAL MATCH (n)-[:COMMUNICATED|TRANSFERRED|USES_PHONE|OWNS_ACCOUNT|INVOLVED_IN]-(m)
        RETURN n.number AS phone, n.account_id AS account, n.name AS name, n.case_id AS case_id, count(m) AS connections
        ORDER BY connections DESC
        LIMIT 10
        """
        result = session.run(query)
        nodes = []
        for record in result:
            identifier = record["phone"] if record["phone"] else (record["account"] if record["account"] else (record["name"] if record["name"] else record["case_id"]))
            if identifier:
                nodes.append({"id": identifier, "connections": record["connections"]})
        return {"suspects": nodes}

@app.get("/api/graph-data")
def get_graph_data(current_user: str = Depends(get_current_user)):
    with driver.session() as session:
        query = """
        MATCH (n)-[r]->(m)
        RETURN id(n) AS source_id, coalesce(n.number, n.account_id, n.name, n.case_id, 'Unknown') AS source_label, labels(n)[0] AS source_type,
               id(m) AS target_id, coalesce(m.number, m.account_id, m.name, m.case_id, 'Unknown') AS target_label, labels(m)[0] AS target_type,
               type(r) AS rel_type
        """
        result = session.run(query)
        nodes = {}
        edges = []
        for record in result:
            s_id, t_id = record["source_id"], record["target_id"]
            if s_id not in nodes:
                nodes[s_id] = {"id": s_id, "label": str(record["source_label"]), "group": record["source_type"]}
            if t_id not in nodes:
                nodes[t_id] = {"id": t_id, "label": str(record["target_label"]), "group": record["target_type"]}
            edges.append({"from": s_id, "to": t_id, "label": record["rel_type"]})
        return {"nodes": list(nodes.values()), "edges": edges}

@app.get("/api/shortest-path")
def get_shortest_path(source: str, target: str, current_user: str = Depends(get_current_user)):
    with driver.session() as session:
        query = """
        MATCH (start) WHERE start.number = $source OR start.account_id = $source OR start.name = $source OR start.case_id = $source
        MATCH (end) WHERE end.number = $target OR end.account_id = $target OR end.name = $target OR end.case_id = $target
        MATCH path = shortestPath((start)-[*]-(end))
        RETURN [n in nodes(path) | id(n)] AS path_nodes
        """
        result = session.run(query, source=source, target=target)
        record = result.single()
        
        if record and record["path_nodes"]:
            return {"path": record["path_nodes"]}
        return {"path": []}

@app.post("/api/upload")
async def upload_intelligence(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    os.makedirs("data", exist_ok=True)
    file_path = f"data/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        df = pd.read_csv(file_path)
        columns = df.columns.str.lower().tolist()
        
        with driver.session() as session:
            for _, row in df.iterrows():
                case_id = str(row['case_id']) if 'case_id' in columns and pd.notna(row['case_id']) else "Case 101 - Hawala Extortion"
                session.run("MERGE (c:Case {case_id: $cid})", cid=case_id)
                
                if "caller" in columns and "receiver" in columns:
                    person_name = str(row['name']) if 'name' in columns and pd.notna(row['name']) else "Unknown Suspect"
                    session.run("""
                        MERGE (c:Case {case_id: $cid})
                        MERGE (p:Person {name: $pname})
                        MERGE (p)-[:INVOLVED_IN]->(c)
                        MERGE (ph1:Phone {number: $caller})
                        MERGE (ph2:Phone {number: $receiver})
                        MERGE (p)-[:USES_PHONE]->(ph1)
                        MERGE (ph1)-[:COMMUNICATED {timestamp: $timestamp, duration: $duration}]->(ph2)
                    """, cid=case_id, pname=person_name, caller=str(row['caller']), receiver=str(row['receiver']), timestamp=str(row.get('timestamp', '')), duration=int(row.get('duration', 0)))
                
                if "sender_acc" in columns and "receiver_acc" in columns:
                    person_name = str(row['name']) if 'name' in columns and pd.notna(row['name']) else "Unknown Holder"
                    session.run("""
                        MERGE (c:Case {case_id: $cid})
                        MERGE (p:Person {name: $pname})
                        MERGE (p)-[:INVOLVED_IN]->(c)
                        MERGE (a1:BankAccount {account_id: $sender})
                        MERGE (a2:BankAccount {account_id: $receiver})
                        MERGE (p)-[:OWNS_ACCOUNT]->(a1)
                        MERGE (a1)-[:TRANSFERRED {amount: $amount, timestamp: $timestamp}]->(a2)
                    """, cid=case_id, pname=person_name, sender=str(row['sender_acc']), receiver=str(row['receiver_acc']), amount=float(row.get('amount', 0.0)), timestamp=str(row.get('timestamp', '')))

        return {"message": f"Master multi-case intelligence file '{file.filename}' processed!"}
    except Exception as e:
        return {"message": f"File saved, but parsing failed. Error: {str(e)}"}