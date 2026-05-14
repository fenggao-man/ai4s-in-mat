from pathlib import Path
from retrieval_main import index_knowledge_graph

def index_all():
    artifacts_root = Path("artifacts/ocr")
    if not artifacts_root.exists():
        print("No artifacts found.")
        return

    for doc_dir in artifacts_root.iterdir():
        if not doc_dir.is_dir():
            continue
        
        run_dirs = sorted([d for d in doc_dir.iterdir() if d.is_dir() and d.name.startswith("run_")])
        if not run_dirs:
            continue
            
        latest_run = run_dirs[-1]
        graph_path = latest_run / "knowledge_graph" / "entity_graph_fused.json"
        md_path = latest_run / "document.md"
        
        if graph_path.exists():
            print(f"[*] Indexing {doc_dir.name}...")
            try:
                result = index_knowledge_graph(graph_path, document_markdown_path=md_path)
                print(f"    [+] Done: {result['node_count']} nodes, {result['chunk_count']} chunks.")
            except Exception as e:
                print(f"    [-] Failed: {e}")

if __name__ == "__main__":
    index_all()
