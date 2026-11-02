"""Connectivity-based series/parallel drawing plans; no electrical simulation."""

from dataclasses import dataclass, field


@dataclass
class DrawingPlan:
    placements: dict = field(default_factory=dict)
    # Each net owns a list of orthogonal polylines in scene coordinates.
    routes: dict = field(default_factory=dict)

    def route(self, net, *points):
        self.routes.setdefault(net, []).append(points)


@dataclass
class Branch:
    start: str
    end: str
    component: object = None
    children: tuple = ()
    kind: str = "component"

    @property
    def width(self):
        if self.kind == "parallel":
            return sum(child.width for child in self.children)
        if self.kind == "series":
            return max(child.width for child in self.children)
        return 320

    @property
    def height(self):
        if self.kind == "series":
            return sum(child.height for child in self.children)
        if self.kind == "parallel":
            return max(child.height for child in self.children)
        return 220


def reachable(edges, start, blocked=None):
    visited, pending = set(), [start]
    while pending:
        node = pending.pop()
        if node == blocked or node in visited:
            continue
        visited.add(node)
        for _, a, b in edges:
            if a == node and b not in visited:
                pending.append(b)
            elif b == node and a not in visited:
                pending.append(a)
    return visited


def split_branch(edges, start, end):
    """Decompose a two-terminal series/parallel graph, or return None."""
    if not edges or start == end or any(a == b for _, a, b in edges):
        return None
    if len(edges) == 1:
        component, a, b = edges[0]
        return Branch(start, end, component) if {a, b} == {start, end} else None
    nodes = {node for _, a, b in edges for node in (a, b)}
    if not nodes <= reachable(edges, start) or end not in nodes:
        return None

    # An articulation node separates consecutive sections of a series branch.
    for middle in sorted(nodes - {start, end}):
        left_nodes = reachable(edges, start, blocked=middle)
        if end in left_nodes:
            continue
        left = [edge for edge in edges if edge[1] in left_nodes or edge[2] in left_nodes]
        right = [edge for edge in edges if edge not in left]
        if not left or not right:
            continue
        a, b = split_branch(left, start, middle), split_branch(right, middle, end)
        if a is not None and b is not None:
            return Branch(start, end, children=(a, b), kind="series")

    # Remove boundary nodes: remaining islands are separate parallel branches.
    internal = nodes - {start, end}
    groups = []
    while internal:
        first = min(internal)
        island, pending = set(), [first]
        while pending:
            node = pending.pop()
            if node in island or node in (start, end):
                continue
            island.add(node)
            for _, a, b in edges:
                if a == node:
                    pending.append(b)
                elif b == node:
                    pending.append(a)
        internal -= island
        groups.append([edge for edge in edges if edge[1] in island or edge[2] in island])
    groups.extend([[edge] for edge in edges if {edge[1], edge[2]} == {start, end}])
    # Stable component order, independent of node/terminal list order.
    order = {edge[0].id: index for index, edge in enumerate(edges)}
    groups.sort(key=lambda group: min(order[edge[0].id] for edge in group))
    if len(groups) < 2:
        return None
    children = tuple(split_branch(group, start, end) for group in groups)
    if any(child is None for child in children):
        return None
    return Branch(start, end, children=children, kind="parallel")


def draw_branch(plan, branch, x, top, height, terminal_nodes):
    bottom = top + height
    if branch.kind == "component":
        component = branch.component
        forward = terminal_nodes[(component.id, "1")] == branch.start
        rotation = 90 if forward else 270
        center = top + height / 2
        plan.placements[component.id] = (x, center, rotation)
        plan.route(branch.start, (x, top), (x, center - 60))
        plan.route(branch.end, (x, center + 60), (x, bottom))
        if component.type == "potentiometer":
            # A vertical track's wiper points left (90°) or right (270°).
            direction = -1 if forward else 1
            net = terminal_nodes[(component.id, "3")]
            plan.route(net, (x + direction * 50, center), (x + direction * 100, center))
    elif branch.kind == "series":
        cursor = top
        for child in branch.children:
            child_height = height * child.height / branch.height
            draw_branch(plan, child, x, cursor, child_height, terminal_nodes)
            cursor += child_height
    else:
        cursor = x - branch.width / 2
        centers = []
        for child in branch.children:
            child_x = cursor + child.width / 2
            centers.append(child_x)
            draw_branch(plan, child, child_x, top, height, terminal_nodes)
            cursor += child.width
        plan.route(branch.start, (min(centers), top), (max(centers), top))
        plan.route(branch.end, (min(centers), bottom), (max(centers), bottom))


def series_parallel_layout(circuit):
    """Lay out a single source and series/parallel load as a rectangular ladder.

    Non-series/parallel networks retain the renderer's generic fallback. A
    potentiometer is laid out as a track only when its wiper is an unloaded net.
    This is a drawing decision, not a reduction of the electrical model.
    """
    sources = [c for c in circuit.components if c.type == "voltage_source"]
    if len(sources) != 1:
        return None
    nodes = circuit.terminal_nodes()
    source = sources[0]
    start, end = nodes[(source.id, "1")], nodes[(source.id, "2")]
    nets = {net.id: net for net in circuit.nets}
    edges = []
    for component in circuit.components:
        if component.id == source.id:
            continue
        if component.type == "potentiometer" and len(nets[nodes[(component.id, "3")]].terminals) != 1:
            return None
        edges.append((component, nodes[(component.id, "1")], nodes[(component.id, "2")]))
    branch = split_branch(edges, start, end)
    if branch is None:
        return None
    plan = DrawingPlan()
    top, height, source_x = 80, branch.height, 100
    load_x = 300 + branch.width / 2
    plan.placements[source.id] = (source_x, top + height / 2, 90)
    draw_branch(plan, branch, load_x, top, height, nodes)
    plan.route(start, (source_x, top + height / 2 - 60), (source_x, top), (load_x, top))
    plan.route(end, (source_x, top + height / 2 + 60), (source_x, top + height), (load_x, top + height))
    return plan


def open_series_parallel_layout(circuit):
    """Arrange dangling branches as ladders, leaving a visible gap to the rail.

    Temporary endpoint assignments determine positions only. Actual nets and the
    solver input are never merged; each dangling wire keeps its original net ID.
    """
    from dataclasses import replace
    from itertools import product

    sources = [c for c in circuit.components if c.type == "voltage_source"]
    if len(sources) != 1:
        return None
    source = sources[0]
    nodes = circuit.terminal_nodes()
    start, end = nodes[(source.id, "1")], nodes[(source.id, "2")]
    if start == end:
        return None
    dangling = [net for net in circuit.nets if len(net.terminals) == 1
                and net.terminals[0].component_id != source.id
                and net.terminals[0].terminal != "3"
                and net.id not in (start, end)]
    if not dangling or len(dangling) > 6:
        return None
    for targets in product((end, start), repeat=len(dangling)):
        assignments = dict(zip((net.id for net in dangling), targets))
        merged = {}
        for net in circuit.nets:
            merged.setdefault(assignments.get(net.id, net.id), []).extend(net.terminals)
        template = circuit.nets[0]
        virtual = replace(circuit, nets=tuple(replace(template, id=nid, terminals=tuple(refs))
                                              for nid, refs in merged.items()))
        plan = series_parallel_layout(virtual)
        if plan is None:
            continue
        valid = True
        for net, target in zip(dangling, targets):
            ref = net.terminals[0]
            x, y, rotation = plan.placements[ref.component_id]
            dx, dy = (-60, 0) if ref.terminal == "1" else (60, 0)
            for _ in range(int(rotation) % 360 // 90):
                dx, dy = -dy, dx
            terminal = (x + dx, y + dy)
            route = next((route for route in plan.routes[target]
                          if len(route) == 2 and terminal in route), None)
            if route is None:
                valid = False
                break
            rail = route[1] if route[0] == terminal else route[0]
            distance = abs(rail[0] - terminal[0]) + abs(rail[1] - terminal[1])
            if distance <= 24:
                valid = False
                break
            tip = (rail[0] + (terminal[0] - rail[0]) * 20 / distance,
                   rail[1] + (terminal[1] - rail[1]) * 20 / distance)
            plan.routes[target].remove(route)
            plan.route(net.id, terminal, tip)
        if valid:
            return plan
    return None
