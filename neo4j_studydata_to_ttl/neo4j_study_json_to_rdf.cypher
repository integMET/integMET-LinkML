MATCH (n:Study)
OPTIONAL MATCH (n)-[r1:Metadata_Species|Metadata_MeSH|HAS_GO_ANNOTATION|HAS_DATA]-(m)
OPTIONAL MATCH (n)-[r3:BELONGS_TO_STUDY]-(m1:AnalyticsGroup)
OPTIONAL MATCH (m1)-[r2:HAS_ANALYSIS_TYPE]-(l)

WITH
  collect(DISTINCT n) + collect(DISTINCT m) + collect(DISTINCT m1) + collect(DISTINCT l) AS allNodes,
  collect(DISTINCT r1) + collect(DISTINCT r2) + collect(DISTINCT r3) AS allRels

WITH
  [x IN allNodes WHERE x IS NOT NULL] AS rawNodes,
  [x IN allRels WHERE x IS NOT NULL] AS rawRels

UNWIND rawNodes AS node
WITH collect(DISTINCT node) AS nodes, rawRels

UNWIND rawRels AS rel
WITH nodes, collect(DISTINCT rel) AS rels

RETURN {
  nodes: [
    node IN nodes |
    {
      elementId: elementId(node),
      identifier: coalesce(node.Nodeid, elementId(node)),
      labels: labels(node),
      properties: properties(node)
    }
  ],
  relationships: [
    rel IN rels |
    {
      elementId: elementId(rel),
      type: type(rel),
      startElementId: elementId(startNode(rel)),
      endElementId: elementId(endNode(rel)),
      startIdentifier: coalesce(startNode(rel).Nodeid, elementId(startNode(rel))),
      endIdentifier: coalesce(endNode(rel).Nodeid, elementId(endNode(rel))),
      properties: properties(rel)
    }
  ]
} AS graph_json