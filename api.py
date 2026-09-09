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

# Allow the frontend to talk to the backend
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
PASSWORD = "janey7749" # <-- Put your real password here!
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

# --- SECURITY SETTINGS ---
SECRET_KEY = "super-secret-police-key"  
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

# Hackathon mock database for officers
OFFICER_DB = {
    "badge123": {
        "username": "badge123",
        "password": "securepassword",
        "name": "Lead Investigator"
    }
}

# --- SECURITY ROUTES (THE FRONT GATE) ---
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


# --- INTELLIGENCE ROUTES (SECURED) ---

@app.get("/api/network-stats")
def get_network_stats(current_user: str = Depends(get_current_user)):
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
                nodes.append({"id": identifier, "connections": record["connections"]})
        return {"suspects": nodes}

@app.get("/api/graph-data")
def get_graph_data(current_user: str = Depends(get_current_user)):
    with driver.session() as session:
        query = """
        MATCH (n)-[r]->(m)
        RETURN id(n) AS source_id, coalesce(n.number, n.account_id) AS source_label, labels(n)[0] AS source_type,
               id(m) AS target_id, coalesce(m.number, m.account_id) AS target_label, labels(m)[0] AS target_type,
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
        MATCH (start) WHERE start.number = $source OR start.account_id = $source
        MATCH (end) WHERE end.number = $target OR end.account_id = $target
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
        with driver.session() as session:
            if "cdr" in file.filename.lower():
                for _, row in df.iterrows():
                    session.run("""
                        MERGE (c1:Phone {number: $caller})
                        MERGE (c2:Phone {number: $receiver})
                        MERGE (c1)-[:COMMUNICATED {timestamp: $timestamp, duration: $duration}]->(c2)
                    """, caller=row['caller'], receiver=row['receiver'], timestamp=str(row['timestamp']), duration=int(row['duration']))
            elif "transaction" in file.filename.lower():
                for _, row in df.iterrows():
                    session.run("""
                        MERGE (a1:BankAccount {account_id: $sender})
                        MERGE (a2:BankAccount {account_id: $receiver})
                        MERGE (a1)-[:TRANSFERRED {amount: $amount, timestamp: $timestamp}]->(a2)
                    """, sender=row['sender_acc'], receiver=row['receiver_acc'], amount=float(row['amount']), timestamp=str(row['timestamp']))
        return {"message": f"Intelligence file '{file.filename}' uploaded and mapped!"}
    except Exception as e:
        return {"message": f"File saved, but graph ingestion failed. Error: {str(e)}"}