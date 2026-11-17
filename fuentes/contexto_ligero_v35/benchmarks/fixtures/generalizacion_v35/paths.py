from policy_config import POLICY_LIMIT

def normalize_path(path):
    return path.strip()

def remove_controls(path):
    return path.replace("\0", "")

def reject_traversal(path):
    return ".." not in path

def safe_path(path):
    path = remove_controls(normalize_path(path))
    if not reject_traversal(path):
        return None
    return path[:POLICY_LIMIT]

def safe_path_statistics():
    return 1
