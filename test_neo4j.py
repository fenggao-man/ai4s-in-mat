import os
from pathlib import Path
from neo4j import GraphDatabase
from scr.knowledge_graph.llm_client import load_env_file

def test_neo4j_connection():
    # 1. 加载配置
    project_root = Path(__file__).resolve().parent
    env_file = project_root / ".env"
    print(f"[*] Loading env from: {env_file}")
    load_env_file(env_file)

    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    database = os.environ.get("NEO4J_DATABASE", "neo4j")

    print(f"[*] Attempting to connect to: {uri}")
    print(f"[*] Database: {database}")
    print(f"[*] User: {user}")

    # 2. 尝试连接并查询
    driver = None
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        # 验证连接是否有效
        driver.verify_connectivity()
        print("[+] Connection successful!")

        with driver.session(database=database) as session:
            # 查询数据库中的节点总数
            print("[*] Counting nodes in database...")
            result = session.run("MATCH (n) RETURN count(n) AS node_count")
            node_count = result.single()["node_count"]
            print(f"[+] Found {node_count} nodes in database '{database}'.")

            # 如果有数据，拉取前 5 个节点的标签
            if node_count > 0:
                print("[*] Fetching labels of first 5 nodes...")
                result = session.run("MATCH (n) RETURN labels(n) as labels LIMIT 5")
                for record in result:
                    print(f"    - Labels: {record['labels']}")
            else:
                print("[!] Database is empty.")

    except Exception as e:
        print(f"[-] Connection failed!")
        print(f"[-] Error: {e}")
    finally:
        if driver:
            driver.close()
            print("[*] Driver closed.")

if __name__ == "__main__":
    test_neo4j_connection()
