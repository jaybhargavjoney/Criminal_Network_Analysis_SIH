import re
import spacy
from neo4j import GraphDatabase

# 1. Neo4j Connection Configuration
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "janey7749" # Replace with your Neo4j password

# 2. Load the spaCy NLP model
nlp = spacy.load("en_core_web_sm")

# 3. Sample Crime Narrative (Unstructured Intelligence Report)
fir_text = """
On 12th March, intelligence intercepted suspect Rajesh Kumar alias Raju communicating 
with Sunil Verma regarding an illegal consignment delivery in Majestic. Sunil Verma coordinates 
finances with Anita Rao. Primary contact number retrieved for Rajesh Kumar is +91-9876543210.
"""

def extract_entities(text):
    """Extracts people, locations, and phone numbers from raw text."""
    doc = nlp(text)
    
    # NLP extraction for persons and locations
    persons = list(set([ent.text.strip() for ent in doc.ents if ent.label_ == "PERSON"]))
    locations = list(set([ent.text.strip() for ent in doc.ents if ent.label_ in ["GPE", "LOC"]]))
    
    # Regex extraction for phone numbers
    phone_pattern = r"(?:\+91[-\s]?)?[6-9]\d{9}"
    phones = list(set(re.findall(phone_pattern, text)))
    
    return persons, locations, phones

def populate_graph(tx, persons, locations, phones):
    """Inserts extracted entities and links them into Neo4j."""
    # Create Person Nodes
    for person in persons:
        tx.run("MERGE (p:Person {name: $name})", name=person)
        
    # Create Location Nodes
    for loc in locations:
        tx.run("MERGE (l:Location {name: $name})", name=loc)
        
    # Create Phone Nodes
    for phone in phones:
        tx.run("MERGE (ph:Phone {number: $number})", number=phone)
        
    # Establish Relationships from the narrative context
    # Link suspects who were co-mentioned
    if "Rajesh Kumar" in persons and "Sunil Verma" in persons:
        tx.run("""
            MATCH (a:Person {name: 'Rajesh Kumar'}), (b:Person {name: 'Sunil Verma'})
            MERGE (a)-[:COMMUNICATED_WITH {intel_source: "FIR_001"}]->(b)
        """)
        
    if "Sunil Verma" in persons and "Anita Rao" in persons:
        tx.run("""
            MATCH (a:Person {name: 'Sunil Verma'}), (b:Person {name: 'Anita Rao'})
            MERGE (a)-[:COORDINATES_FINANCE_WITH]->(b)
        """)
        
    # Associate phone number with suspect
    if "Rajesh Kumar" in persons and phones:
        tx.run("""
            MATCH (p:Person {name: 'Rajesh Kumar'}), (ph:Phone {number: $phone})
            MERGE (p)-[:USES_PHONE]->(ph)
        """, phone=phones[0])

def main():
    print("Extracting entities with AI...")
    persons, locations, phones = extract_entities(fir_text)
    print(f"Extracted Suspects: {persons}")
    print(f"Extracted Locations: {locations}")
    print(f"Extracted Phone Numbers: {phones}")

    print("\nConnecting to Neo4j database...")
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    
    with driver.session() as session:
        session.execute_write(populate_graph, persons, locations, phones)
        print("Data successfully loaded into knowledge graph!")
        
    driver.close()

if __name__ == "__main__":
    main()