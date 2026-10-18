# Every Cypher query SecondOrder runs

All queries are hand-written and parameterised (`secondorder/engine.py`, dict `Q`). The LLM never writes Cypher.
Graphs: `so:<sid>:world` (ground truth, witnesses) and `so:<sid>:mind:<agent>` (one per agent).

## `meta_get`
Load scenario metadata (step counter, chapter, agents).
```cypher
MATCH (m:Meta)
RETURN m.seq, m.chapter, m.room, m.agents, m.depth, m.trust
```

## `meta_set`
Persist scenario metadata.
```cypher
MERGE (m:Meta {id: 0})
SET m.seq = $seq, m.chapter = $chapter, m.room = $room, m.agents = $agents, m.depth = $depth, m.trust = $trust
```

## `present`
Who is in a room right now (the witnesses of the next event).
```cypher
MATCH (a:Agent)-[:IN]->(:Room {name: $room})
RETURN a.name
ORDER BY a.name
```

## `where_is`
Which room an agent is in.
```cypher
MATCH (a:Agent {name: $agent})-[:IN]->(r:Room)
RETURN r.name
```

## `enter`
Agents enter a room.
```cypher
UNWIND $agents AS name
MERGE (a:Agent {name: name})
MERGE (r:Room {name: $room})
CREATE (a)-[:IN {since: $t, chapter: $chapter}]->(r)
```

## `exit`
An agent leaves; the exit time is kept (the trust rule needs exit order).
```cypher
MATCH (a:Agent {name: $agent})-[i:IN]->(r:Room)
DELETE i
CREATE (a)-[:EXITED {t: $t, chapter: $chapter}]->(r)
RETURN r.name
```

## `event`
Record an event and WHO WITNESSED it.
```cypher
CREATE (ev:Event {seq: $t, kind: $kind, text: $text, room: $room, actor: $actor, entity: $entity, value: $value, chapter: $chapter})
WITH ev
UNWIND $witnesses AS w
MERGE (a:Agent {name: w})
CREATE (a)-[:WITNESSED]->(ev)
```

## `event_links`
Link the event to its actor and the entity it is about.
```cypher
MATCH (ev:Event {seq: $t})
OPTIONAL
MATCH (actor:Agent {name: $actor})
FOREACH (_ IN CASE WHEN actor IS NULL THEN [] ELSE [1] END |
CREATE (actor)-[:PERFORMED]->(ev))
WITH ev
OPTIONAL
MATCH (e:Entity {name: $entity})
FOREACH (_ IN CASE WHEN e IS NULL THEN [] ELSE [1] END |
CREATE (ev)-[:ABOUT]->(e))
```

## `set_state`
Change the world state of an entity (and where it is visible).
```cypher
MERGE (e:Entity {name: $entity})
WITH e
OPTIONAL
MATCH (e)-[old:IS]->()
DELETE old
WITH e
MERGE (v:Value {name: $value})
CREATE (e)-[:IS {t: $t}]->(v)
WITH v
WHERE $room IS NOT NULL
MERGE (r:Room {name: $room})
MERGE (v)-[:LOCATED_IN]->(r)
```

## `visible_in_room`
What an entrant sees on entering a room.
```cypher
MATCH (e:Entity)-[:IS]->(v:Value)-[:LOCATED_IN]->(:Room {name: $room})
RETURN e.name, v.name
```

## `truth`
Ground truth of an entity.
```cypher
MATCH (e:Entity {name: $entity})-[:IS]->(v:Value)
RETURN v.name
```

## `entities`
All tracked entities.
```cypher
MATCH (e:Entity)
RETURN e.name
ORDER BY e.name
```

## `trusts`
Hi-ToM trust rule as a graph predicate: believe a speaker who left the room after you (or if you were never there).
```cypher
MATCH (s:Agent {name: $speaker})
OPTIONAL
MATCH (s)-[es:EXITED {chapter: $chapter}]->()
OPTIONAL
MATCH (:Agent {name: $listener})-[el:EXITED {chapter: $chapter}]->()
RETURN el IS NULL OR (es IS NOT NULL AND es.t > el.t)
```

## `told`
Record who told whom what (public/private, trusted or not).
```cypher
MERGE (s:Agent {name: $speaker})
MERGE (l:Agent {name: $listener})
CREATE (s)-[:TOLD {t: $t, entity: $entity, value: $value, public: $public, trusted: $trusted}]->(l)
```

## `missed_events`
The event a perspective did not witness (why it is wrong).
```cypher
MATCH (ev:Event)-[:ABOUT]->(:Entity {name: $entity})
WHERE ev.kind IN ['observe', 'move'] AND ev.seq > $since AND NOT (:Agent {name: $agent})-[:WITNESSED]->(ev)
RETURN ev.seq, ev.text, ev.actor, ev.room
ORDER BY ev.seq DESC LIMIT 1
```

## `event_by_seq`
An event with its witnesses.
```cypher
MATCH (ev:Event {seq: $t})
OPTIONAL
MATCH (w:Agent)-[:WITNESSED]->(ev)
RETURN ev.seq, ev.kind, ev.text, ev.room, collect(w.name)
```

## `timeline`
Full event log with witnesses.
```cypher
MATCH (ev:Event)
OPTIONAL
MATCH (w:Agent)-[:WITNESSED]->(ev)
RETURN ev.seq, ev.kind, ev.text, ev.room, ev.actor, ev.entity, ev.value, collect(w.name)
ORDER BY ev.seq
```

## `info_path`
Who-told-whom path between two agents via FalkorDB's algo.SPpaths over TOLD edges.
```cypher
MATCH (s:Agent {name: $src}), (d:Agent {name: $dst})
CALL algo.SPpaths({sourceNode: s, targetNode: d, relTypes: ['TOLD'], pathCount: 1, maxLen: 6})
YIELD path
RETURN [n IN nodes(path) | n.name]
```

## `ensure_perspectives`
Create perspective nodes (lazily, only when a perspective first diverges).
```cypher
UNWIND $nodes AS n
MERGE (p:Perspective {chain: n.chain}) ON
CREATE
SET p.depth = n.depth, p.agents = n.agents, p.owner = $owner, p.created = $t
```

## `ensure_inherits`
Link child perspective -> parent.
```cypher
UNWIND $links AS l
MATCH (c:Perspective {chain: l.c}), (p:Perspective {chain: l.p})
MERGE (c)-[:INHERITS]->(p)
```

## `materialise`
COPY-ON-WRITE: before an update, freeze the inherited belief of child perspectives that did not witness the event.
```cypher
UNWIND $chains AS ch
MATCH (p:Perspective {chain: ch})
WHERE NOT (p)-[:BELIEVES {entity: $entity, active: true}]->()
OPTIONAL
MATCH path = (p)-[:INHERITS*1..6]->(q:Perspective)-[b:BELIEVES {entity: $entity, active: true}]->(v:Value)
WITH p, q, b, v, length(path) AS d
ORDER BY d ASC
WITH p, collect([v.name, b.via, b.event, b.src, q.chain])[0] AS best
WITH p, CASE WHEN best[0] IS NULL THEN [$unknown, 'unknown', null, null, null] ELSE best END AS best
MERGE (v2:Value {name: best[0]})
CREATE (p)-[:BELIEVES {entity: $entity, active: true, t: $t, via: 'retained', orig_via: best[1], event: best[2], src: best[3], from_chain: best[4]}]->(v2)
RETURN count(p)
```

## `update`
Write the new belief into every perspective whose members all witnessed/heard the event (old belief closed with `until`).
```cypher
UNWIND $chains AS ch
MATCH (p:Perspective {chain: ch})
OPTIONAL
MATCH (p)-[old:BELIEVES {entity: $entity, active: true}]->()
SET old.active = false, old.until = $t
WITH DISTINCT p
MERGE (v:Value {name: $value})
CREATE (p)-[:BELIEVES {entity: $entity, active: true, t: $t, via: $via, event: $event, src: $src}]->(v)
RETURN count(p)
```

## `resolve`
READ a nested belief: nearest perspective on the INHERITS path that holds an active belief.
```cypher
MATCH (p:Perspective)
WHERE p.chain IN $prefixes
WITH p
ORDER BY p.depth DESC LIMIT 1
MATCH path = (p)-[:INHERITS*0..6]->(q:Perspective)-[b:BELIEVES {entity: $entity, active: true}]->(v:Value)
RETURN v.name, b.via, b.t, b.event, b.src, q.chain, length(path), b.orig_via, b.from_chain
ORDER BY length(path) ASC LIMIT 1
```

## `resolve_at`
TIME TRAVEL: what did this perspective believe at step N.
```cypher
MATCH (p:Perspective)
WHERE p.chain IN $prefixes AND p.created <= $at
WITH p
ORDER BY p.depth DESC LIMIT 1
MATCH path = (p)-[:INHERITS*0..6]->(q:Perspective)-[b:BELIEVES {entity: $entity}]->(v:Value)
WHERE b.t <= $at AND (b.until IS NULL OR b.until > $at)
RETURN v.name, b.via, b.t, b.event, b.src, q.chain, length(path), b.orig_via, b.from_chain
ORDER BY length(path) ASC LIMIT 1
```

## `mind_stats`
Size of a mind graph.
```cypher
MATCH (p:Perspective)
OPTIONAL
MATCH (p)-[b:BELIEVES]->()
RETURN count(DISTINCT p), count(b), sum(CASE WHEN b.active THEN 1 ELSE 0 END)
```

## `perspectives`
All perspectives of an agent with their own beliefs.
```cypher
MATCH (p:Perspective)
OPTIONAL
MATCH (p)-[b:BELIEVES {active: true}]->(v:Value)
RETURN p.chain, p.depth, collect([b.entity, v.name, b.via, b.t])
ORDER BY p.depth, p.chain
```
