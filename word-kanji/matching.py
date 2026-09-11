"""Maximum cardinality matching in a general undirected graph (blossom contraction)."""
from collections import deque

def maximum_matching(graph):
    n = len(graph)
    match = [-1] * n

    def augment(root):
        parent = [-1] * n
        base = list(range(n))
        used = [False] * n
        queue = deque([root])
        used[root] = True

        def lca(a, b):
            seen = [False] * n
            while True:
                a = base[a]
                seen[a] = True
                if match[a] == -1:
                    break
                a = parent[match[a]]
            while True:
                b = base[b]
                if seen[b]:
                    return b
                b = parent[match[b]]

        def mark_path(v, b, child, blossom):
            while base[v] != b:
                blossom[base[v]] = blossom[base[match[v]]] = True
                parent[v] = child
                child = match[v]
                v = parent[match[v]]
        while queue:
            v = queue.popleft()
            for u in graph[v]:
                if base[v] == base[u] or match[v] == u:
                    continue
                if u == root or (match[u] != -1 and parent[match[u]] != -1):
                    b = lca(v, u)
                    blossom = [False] * n
                    mark_path(v, b, u, blossom)
                    mark_path(u, b, v, blossom)
                    for i in range(n):
                        if blossom[base[i]]:
                            base[i] = b
                            if not used[i]:
                                used[i] = True
                                queue.append(i)
                elif parent[u] == -1:
                    parent[u] = v
                    if match[u] == -1:
                        current = u
                        while current != -1:
                            previous = parent[current]
                            following = match[previous] if previous != -1 else -1
                            match[current] = previous
                            if previous != -1:
                                match[previous] = current
                            current = following
                        return True
                    u = match[u]
                    used[u] = True
                    queue.append(u)
        return False
    for vertex in range(n):
        if match[vertex] == -1:
            augment(vertex)
    assert all((m == -1 or (match[m] == v and m in graph[v]) for v, m in enumerate(match)))
    return match
