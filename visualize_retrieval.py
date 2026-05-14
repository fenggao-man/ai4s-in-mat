import os
import json
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from neo4j import GraphDatabase
from scr.knowledge_graph.llm_client import load_env_file

from scr.knowledge_graph.sqlite_retrieval import (
    DEFAULT_DB_PATH,
    search_knowledge_graph,
)

app = Flask(__name__)
CORS(app)

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / DEFAULT_DB_PATH
ENV_FILE = PROJECT_ROOT / ".env"

# Load Neo4j config
load_env_file(ENV_FILE)
NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USER = os.environ.get("NEO4J_USER")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

def get_neo4j_data(query_text):
    if not NEO4J_URI:
        return {"nodes": [], "edges": []}
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    nodes = []
    edges = []
    node_ids = set()
    edge_keys = set()
    
    # More robust path-based Cypher query
    cypher = """
    MATCH (n)
    WHERE toLower(n.display_name) CONTAINS toLower($q) 
       OR toLower(n.name) CONTAINS toLower($q) 
       OR toLower(n.title) CONTAINS toLower($q)
    WITH n LIMIT 20
    OPTIONAL MATCH p = (n)-[*1..2]-(m)
    RETURN n, p
    """
    
    def get_id(obj):
        # Handle both legacy .id and new .element_id
        if hasattr(obj, 'element_id'):
            return str(obj.element_id)
        return str(obj.id)

    def process_node(node_obj, is_hit=False):
        if not node_obj: return None
        nid = get_id(node_obj)
        if nid not in node_ids:
            nodes.append({
                "node_id": nid,
                "type": list(node_obj.labels)[0] if node_obj.labels else "Unknown",
                "display_name": node_obj.get("display_name") or node_obj.get("name") or node_obj.get("title") or nid,
                "properties_json": json.dumps(dict(node_obj)),
                "is_hit": is_hit
            })
            node_ids.add(nid)
        elif is_hit:
            for n in nodes:
                if n["node_id"] == nid:
                    n["is_hit"] = True
        return nid

    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(cypher, q=query_text)
            for record in result:
                hit_node = record["n"]
                process_node(hit_node, is_hit=True)
                
                path = record["p"]
                if path:
                    # Process all nodes in path
                    for node in path.nodes:
                        process_node(node)
                    # Process all relationships in path
                    for rel in path.relationships:
                        sid = get_id(rel.start_node)
                        tid = get_id(rel.end_node)
                        ekey = f"{sid}-{rel.type}-{tid}"
                        if ekey not in edge_keys:
                            edges.append({
                                "source_id": sid,
                                "target_id": tid,
                                "relation": rel.type
                            })
                            edge_keys.add(ekey)
    except Exception as e:
        print(f"[neo4j] Query error: {e}")
    finally:
        driver.close()
    
    print(f"[neo4j] Search '{query_text}' found {len(nodes)} nodes, {len(edges)} edges")
    return {"nodes": nodes, "edges": edges}

# HTML Template with Vis.js
# ... (HTML remains mostly same, but we'll update the API call info)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AI4S Mat - Knowledge Retrieval Visualization</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style type="text/css">
        body { font-family: sans-serif; margin: 20px; background-color: #f5f7fa; }
        #header { display: flex; gap: 10px; margin-bottom: 20px; align-items: center; }
        #query { flex-grow: 1; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px; }
        button { padding: 10px 20px; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
        button:hover { background-color: #0056b3; }
        #main-container { display: flex; gap: 20px; height: 80vh; }
        #graph-container { flex: 2; background-color: white; border: 1px solid #ddd; border-radius: 8px; position: relative; }
        #info-container { flex: 1; display: flex; flex-direction: column; gap: 20px; overflow-y: auto; }
        .info-box { background-color: white; border: 1px solid #ddd; border-radius: 8px; padding: 15px; }
        .info-box h3 { margin-top: 0; color: #333; border-bottom: 2px solid #007bff; padding-bottom: 5px; }
        .chunk-item { margin-bottom: 15px; padding: 10px; background-color: #f9f9f9; border-left: 4px solid #28a745; font-size: 14px; line-height: 1.5; }
        #node-details { font-size: 14px; }
        pre { white-space: pre-wrap; word-wrap: break-word; background: #eee; padding: 5px; }
    </style>
</head>
<body>
    <div id="header">
        <input type="text" id="query" placeholder="Enter your search query (e.g., catalyst name, property...)" value="ammonia synthesis">
        <button onclick="doSearch()">Search & Visualize</button>
    </div>

    <div id="main-container">
        <div id="graph-container"></div>
        <div id="info-container">
            <div class="info-box">
                <h3>Retrieved Text Chunks</h3>
                <div id="chunks-list">Enter a query to see related text segments...</div>
            </div>
            <div class="info-box">
                <h3>Node Details</h3>
                <div id="node-details">Click a node in the graph to see details...</div>
            </div>
        </div>
    </div>

    <script type="text/javascript">
        let network = null;

        async function doSearch() {
            const query = document.getElementById('query').value;
            if (!query) return;

            document.getElementById('chunks-list').innerHTML = "Searching...";
            
            try {
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();
                
                renderGraph(data);
                renderChunks(data.chunks);
            } catch (error) {
                console.error('Search failed:', error);
                alert('Search failed. Check console for details.');
            }
        }

        function renderGraph(data) {
            const nodes = [];
            const edges = [];
            const nodeIds = new Set();

            // Colors for different node types
            const typeColors = {
                '文档': '#ffc107',
                '催化剂': '#007bff',
                '活性组分': '#28a745',
                '载体': '#17a2b8',
                '助剂': '#6f42c1',
                '性能': '#dc3545',
                '反应条件': '#fd7e14'
            };

            // Process retrieved subgraph
            if (data.subgraph && data.subgraph.nodes) {
                data.subgraph.nodes.forEach(n => {
                    if (!nodeIds.has(n.node_id)) {
                        nodes.push({
                            id: n.node_id,
                            label: n.display_name || n.node_id,
                            title: n.type,
                            color: typeColors[n.type] || '#6c757d',
                            font: { color: n.is_hit ? 'black' : 'white', weight: n.is_hit ? 'bold' : 'normal' },
                            size: n.is_hit ? 35 : 20,
                            borderWidth: n.is_hit ? 4 : 1,
                            borderColor: '#333',
                            shadow: n.is_hit,
                            properties: JSON.parse(n.properties_json)
                        });
                        nodeIds.add(n.node_id);
                    }
                });

                data.subgraph.edges.forEach(e => {
                    edges.push({
                        from: e.source_id,
                        to: e.target_id,
                        label: e.relation,
                        arrows: 'to',
                        font: { align: 'middle', size: 12, strokeWidth: 2, strokeColor: '#ffffff' },
                        color: { color: '#848484', highlight: '#007bff' },
                        width: 2
                    });
                });
            }

            const container = document.getElementById('graph-container');
            const graphData = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
            
            const options = {
                nodes: { 
                    shape: 'dot',
                    scaling: { min: 10, max: 30 }
                },
                edges: {
                    smooth: { type: 'continuous' }
                },
                physics: {
                    enabled: true,
                    barnesHut: {
                        gravitationalConstant: -3000,
                        centralGravity: 0.3,
                        springLength: 150,
                        springConstant: 0.04,
                        damping: 0.09,
                        avoidOverlap: 0.1
                    },
                    stabilization: { iterations: 150 }
                },
                interaction: {
                    hover: true,
                    tooltipDelay: 200
                }
            };

            network = new vis.Network(container, graphData, options);

            network.on("click", function (params) {
                if (params.nodes.length > 0) {
                    const nodeId = params.nodes[0];
                    const node = nodes.find(n => n.id === nodeId);
                    showNodeDetails(node);
                }
            });
        }

        function renderChunks(chunks) {
            const list = document.getElementById('chunks-list');
            if (!chunks || chunks.length === 0) {
                list.innerHTML = "No chunks found.";
                return;
            }

            list.innerHTML = chunks.map(c => `
                <div class="chunk-item">
                    <strong>[Doc: ${c.doc_id}]</strong><br>
                    ${c.text.replace(/\\n/g, '<br>')}
                </div>
            `).join('');
        }

        function showNodeDetails(node) {
            const details = document.getElementById('node-details');
            
            // 1. Show Node Properties
            let propsHtml = '<h4>Properties</h4><table style="width:100%; font-size:12px; border-collapse: collapse;">';
            for (const [k, v] of Object.entries(node.properties)) {
                propsHtml += `<tr style="border-bottom: 1px solid #eee;"><td style="font-weight:bold; width:30%; padding: 4px;">${k}:</td><td style="padding: 4px;">${JSON.stringify(v)}</td></tr>`;
            }
            propsHtml += '</table>';

            // 2. Show Related Relationships
            const connectedEdges = network.getConnectedEdges(node.id);
            const edgeData = network.body.data.edges;
            const nodeData = network.body.data.nodes;
            
            let relsHtml = '<h4 style="margin-top:15px;">Relationships</h4><ul style="padding-left: 20px; font-size: 12px;">';
            if (connectedEdges.length > 0) {
                connectedEdges.forEach(edgeId => {
                    const edge = edgeData.get(edgeId);
                    const isFrom = edge.from === node.id;
                    const otherNodeId = isFrom ? edge.to : edge.from;
                    const otherNode = nodeData.get(otherNodeId);
                    const otherLabel = otherNode ? (otherNode.label || otherNodeId) : otherNodeId;
                    
                    if (isFrom) {
                        relsHtml += `<li style="margin-bottom:5px;"><strong>(This)</strong> --[${edge.label}]--> <strong>${otherLabel}</strong></li>`;
                    } else {
                        relsHtml += `<li style="margin-bottom:5px;"><strong>${otherLabel}</strong> --[${edge.label}]--> <strong>(This)</strong></li>`;
                    }
                });
            } else {
                relsHtml += '<li>No relationships found in current view.</li>';
            }
            relsHtml += '</ul>';

            details.innerHTML = `
                <div style="background:#f0f7ff; padding:8px; border-radius:4px; margin-bottom:10px;">
                    <strong>ID:</strong> ${node.id}<br>
                    <strong>Type:</strong> <span style="background:#007bff; color:white; padding:2px 6px; border-radius:10px; font-size:10px;">${node.title}</span>
                </div>
                ${propsHtml}
                ${relsHtml}
            `;
        }

        // Initial search
        window.onload = doSearch;
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 5))
    hops = int(request.args.get('hops', 1))
    
    if not query:
        return jsonify({"error": "Query is required"}), 400
        
    try:
        # 1. Get text chunks from SQLite
        sqlite_result = search_knowledge_graph(
            query=query,
            db_path=DB_PATH,
            limit=limit,
            hops=hops
        )
        
        # 2. Get graph data from Neo4j
        neo4j_data = get_neo4j_data(query)
        
        # 3. Combine
        combined_result = {
            "query": query,
            "chunks": sqlite_result.get("chunks", []),
            "subgraph": neo4j_data  # Use Neo4j data for the visualization
        }
        
        return jsonify(combined_result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Using a fixed port for OpenPreview
    app.run(host='0.0.0.0', port=5005, debug=True)
