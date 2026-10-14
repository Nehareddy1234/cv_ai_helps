from clean_rpc import send_rpc

snap = send_rpc("session.snapshot", {"detail": "full"})
tree = snap.get("result", {}).get("layer_tree", {})

def print_nodes(node, indent=0):
    name = node.get("name") or node.get("id") or "Root"
    vis = node.get("visible")
    item_type = node.get("node_type")
    print(f"{'  '*indent}- {name} (type: {item_type}, visible: {vis})")
    for child in node.get("children", []):
        print_nodes(child, indent + 1)

print_nodes(tree)
