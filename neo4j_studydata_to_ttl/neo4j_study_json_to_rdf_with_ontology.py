from pathlib import Path
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Create RDF outputs (.ttl, .nt, .jsonld) for data and a matching ontology .ttl.

Usage:
    python study_json_to_rdf_with_ontology.py [output_base]

Behavior:
- Reads the Neo4j JSON from INPUT_JSON embedded in the script.
- Writes:
    <output_base>.ttl
    <output_base>.nt
    <output_base>.jsonld
    <output_base>_ontology.ttl
"""

import json
import re
import sys
from collections import defaultdict

from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD

SCHEMA = Namespace("https://schema.org/")
DC = Namespace("http://purl.org/dc/terms/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
PROV = Namespace("http://www.w3.org/ns/prov#")
NFO = Namespace("http://www.semanticdesktop.org/ontologies/2007/03/22/nfo#")
INTEGMET = Namespace("https://example.org/integmet/ontology/")
INTEGMET_STUDY = Namespace("https://integmet.org/studies/")
MESH = Namespace("https://identifiers.org/mesh:")
NCBIGENE = Namespace("https://identifiers.org/ncbigene:")
OMIM = Namespace("https://identifiers.org/omim:")
GO = Namespace("https://identifiers.org/GO:")
METABOLIGHTS = Namespace("https://identifiers.org/metabolights:")
MWSTUDY = Namespace("https://identifiers.org/mw.study:")
TAXONOMY = Namespace("https://identifiers.org/taxonomy:")
CHMO = Namespace("http://purl.obolibrary.org/obo/CHMO_")
PSIMS = Namespace("http://purl.obolibrary.org/obo/MS_")
ANALYSIS_GROUP_RES = Namespace("https://integmet.org/analysis-groups/")
CATEGORY_INFO_RES = Namespace("https://integmet.org/category-info/")
ORGANISM_ANNOTATION_RES = Namespace("https://integmet.org/organism-annotations/")

ANALYTICS_GROUP_LABEL = "AnalyticsGroup"
ANALYTICS_GROUP_TO_STUDY_REL = "BELONGS_TO_STUDY"
ANALYTICS_TYPE_REL = "HAS_ANALYSIS_TYPE"

INPUT_JSON = "/mnt/data/neo4j_query_table_data_2026-4-1.json"
DEFAULT_OUTPUT_BASE = "/mnt/data/study_integmet_annotations_multiformat_grouped"

ONTOLOGY_VERSION = "0.1.9"


def bind_prefixes(g: Graph) -> None:
    g.bind("integmet", INTEGMET)
    g.bind("integmet_study", INTEGMET_STUDY)
    g.bind("integmet_ag", ANALYSIS_GROUP_RES)
    g.bind("integmet_catinfo_res", CATEGORY_INFO_RES)
    g.bind("integmet_organn", ORGANISM_ANNOTATION_RES)
    g.bind("schema", SCHEMA, override=True, replace=True)
    g.bind("dc", DC)
    g.bind("dcat", DCAT)
    g.bind("prov", PROV)
    g.bind("nfo", NFO)
    g.bind("mesh", MESH)
    g.bind("ncbigene", NCBIGENE)
    g.bind("omim", OMIM)
    g.bind("GO", GO)
    g.bind("metabolights", METABOLIGHTS)
    g.bind("mwstudy", MWSTUDY)
    g.bind("taxonomy", TAXONOMY)
    g.bind("chmo", CHMO)
    g.bind("psims", PSIMS)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)


def add_literal(graph: Graph, subject, predicate, value) -> None:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            add_literal(graph, subject, predicate, item)
        return
    if isinstance(value, bool):
        graph.add((subject, predicate, Literal(value, datatype=XSD.boolean)))
    elif isinstance(value, int):
        graph.add((subject, predicate, Literal(value, datatype=XSD.integer)))
    elif isinstance(value, float):
        graph.add((subject, predicate, Literal(value, datatype=XSD.double)))
    else:
        text = str(value)
        if text != "":
            graph.add((subject, predicate, Literal(text)))


def add_en_literal(graph: Graph, subject, predicate, value) -> None:
    text = normalize_text(value)
    if text:
        graph.add((subject, predicate, Literal(text, lang="en")))


def normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_name(value: str) -> str:
    s = str(value).strip()
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s)
    s = s.strip("_")
    if not s:
        s = "value"
    if re.match(r"^[0-9]", s):
        s = "p_" + s
    return s


def iri_fragment(value: str) -> str:
    text = normalize_text(value)
    if not text:
        return "value"
    text = re.sub(r"[^A-Za-z0-9._~-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return "value"
    if re.match(r"^[0-9]", text):
        text = "v_" + text
    return text



def get_study_candidate_value(props: dict):
    """
    Prefer properties["Study"], fall back to properties["Nodeid"].
    """
    study_value = normalize_text(props.get("Study"))
    if study_value:
        return study_value, "Study"

    nodeid_value = normalize_text(props.get("Nodeid"))
    if nodeid_value:
        return nodeid_value, "Nodeid"

    return None, None


def get_study_source_namespace_and_id(study_value):
    text = normalize_text(study_value)
    if text.startswith("MTBLS"):
        return "metabolights", text
    if text.startswith("ST"):
        return "mwstudy", text
    return None, None


def load_graph_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        if not data:
            raise ValueError("Input JSON is an empty list.")
        first = data[0]
    elif isinstance(data, dict):
        first = data
    else:
        raise ValueError("Unsupported top-level JSON structure.")

    if "graph_json" not in first:
        raise ValueError("Missing 'graph_json' key.")

    graph_json = first["graph_json"]
    if "nodes" not in graph_json or "relationships" not in graph_json:
        raise ValueError("graph_json must contain 'nodes' and 'relationships'.")

    return graph_json


def add_annotated_term_from_mesh_identifier(graph: Graph, subject, identifier_value) -> str | None:
    text = normalize_text(identifier_value)
    if not text:
        return None

    if text.startswith("GeneId:"):
        suffix = text[len("GeneId:"):].strip()
        if not suffix:
            return None
        graph.add((subject, INTEGMET.hasAnnotatedNCBIGene, URIRef(str(NCBIGENE) + suffix)))
        return f"ncbigene:{suffix}"

    if text.startswith("OMIM:"):
        suffix = text[len("OMIM:"):].strip()
        if not suffix:
            return None
        graph.add((subject, INTEGMET.hasAnnotatedOMIMEntry, URIRef(str(OMIM) + suffix)))
        return f"omim:{suffix}"

    graph.add((subject, INTEGMET.hasAnnotatedMeSHTerm, URIRef(str(MESH) + text)))
    return f"mesh:{text}"


def add_annotated_go_term(graph: Graph, subject, go_value) -> str | None:
    text = normalize_text(go_value)
    if not text:
        return None

    suffix = text[len("GO:"):].strip() if text.startswith("GO:") else text
    if not suffix:
        return None

    graph.add((subject, INTEGMET.hasAnnotatedGOTerm, URIRef(str(GO) + suffix)))
    return f"GO:{suffix}"


def add_category_info(graph: Graph, subject, study_id: str, props: dict) -> None:
    branch = props.get("category_branch_by_llm")
    category = props.get("category_by_llm")
    subcategory = props.get("subcategory_by_llm")

    if not any(v not in (None, "") for v in [branch, category, subcategory]):
        return

    catinfo = CATEGORY_INFO_RES[iri_fragment(study_id)]
    graph.add((subject, INTEGMET.categoryInfo, catinfo))
    graph.add((catinfo, RDF.type, INTEGMET.StudyCategoryClassification))

    if branch not in (None, ""):
        graph.add((catinfo, INTEGMET.categoryBranch, Literal(str(branch), lang="en")))
    if category not in (None, ""):
        graph.add((catinfo, INTEGMET.category, Literal(str(category), lang="en")))
    if subcategory not in (None, ""):
        graph.add((catinfo, INTEGMET.subcategory, Literal(str(subcategory), lang="en")))


def add_measurement_technique(graph: Graph, subject, analysis_type_value) -> str:
    text = normalize_text(analysis_type_value)
    if not text:
        return "empty"

    predicate = SCHEMA.measurementTechnique

    multi_mapping = {
        "FIA-MS": [CHMO["0000470"], PSIMS["1000058"]],
        "Flow_injection_analysis_MS": [CHMO["0000470"], PSIMS["1000058"]],
        "DI-MS": [CHMO["0000470"], PSIMS["1000060"]],
    }
    if text in multi_mapping:
        for obj in multi_mapping[text]:
            graph.add((subject, predicate, obj))
        return "mapped-multi"

    mapping = {
        "LC-MS": CHMO["0000524"],
        "GC-MS": CHMO["0000497"],
        "CE-MS": CHMO["0000702"],
        "MALDI-MS": CHMO["0000519"],
        "MS": CHMO["0000470"],
        "GC-FID": CHMO["0001736"],
        "ImagingMS": CHMO["0000054"],
    }
    obj = mapping.get(text)
    if obj is not None:
        graph.add((subject, predicate, obj))
        return "mapped"

    graph.add((subject, predicate, Literal(text, datatype=XSD.string)))
    return "literal"



def normalize_ttl_prefixes(path: str) -> None:
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    s = s.replace("@prefix dc1: <http://purl.org/dc/terms/> .", "@prefix dc: <http://purl.org/dc/terms/> .")
    s = s.replace("dc1:", "dc:")
    p.write_text(s, encoding="utf-8")

def build_ontology_graph() -> Graph:
    g = Graph()
    bind_prefixes(g)

    ontology = URIRef(str(INTEGMET))
    g.add((ontology, RDF.type, OWL.Ontology))
    g.add((ontology, DC.title, Literal("IntegMet Ontology", lang="en")))
    g.add((ontology, DC.description, Literal("Ontology for IntegMet-specific study metadata, derived textual summaries, category assignments, annotation links, provenance, and related structural relations.", lang="en")))
    g.add((ontology, DC.creator, Literal("IntegMet project", lang="en")))
    g.add((ontology, DC.created, Literal("2026-03-27", datatype=XSD.date)))
    g.add((ontology, OWL.versionInfo, Literal(ONTOLOGY_VERSION)))
    g.add((ontology, RDFS.label, Literal("IntegMet ontology", lang="en")))
    g.add((ontology, RDFS.comment, Literal("Custom RDF vocabulary used for IntegMet-specific study metadata and structural relations.", lang="en")))

    # Classes
    def add_class(uri, label, comment, superclass=None):
        g.add((uri, RDF.type, OWL.Class))
        g.add((uri, RDFS.label, Literal(label, lang="en")))
        g.add((uri, RDFS.comment, Literal(comment, lang="en")))
        g.add((uri, RDFS.isDefinedBy, ontology))
        if superclass is not None:
            g.add((uri, RDFS.subClassOf, superclass))

    add_class(INTEGMET.Study, "IntegMet study", "A study resource curated in the IntegMet dataset.", DCAT.Dataset)
    add_class(INTEGMET.AnalysisGroup, "Analysis group", "A data-file level grouping within an IntegMet study.")
    add_class(INTEGMET.StudyCategoryClassification, "Study category classification", "Structured category metadata with branch, category, and optional subcategory assigned by IntegMet.")
    add_class(INTEGMET.SourceDerivedOrganismAnnotationSet, "source-derived organism annotation set", "A source-derived set of organism annotations attached to an IntegMet study and explicitly represented as having been obtained from the cited source project rather than inferred independently within IntegMet.")

    # Properties
    def add_obj_prop(uri, label, comment, domain=None, range_=None, subprop=None):
        g.add((uri, RDF.type, OWL.ObjectProperty))
        g.add((uri, RDFS.label, Literal(label, lang="en")))
        g.add((uri, RDFS.comment, Literal(comment, lang="en")))
        g.add((uri, RDFS.isDefinedBy, ontology))
        if domain is not None:
            g.add((uri, RDFS.domain, domain))
        if range_ is not None:
            g.add((uri, RDFS.range, range_))
        if subprop is not None:
            g.add((uri, RDFS.subPropertyOf, subprop))

    def add_data_prop(uri, label, comment, domain=None, range_=None, subprop=None):
        g.add((uri, RDF.type, OWL.DatatypeProperty))
        g.add((uri, RDFS.label, Literal(label, lang="en")))
        g.add((uri, RDFS.comment, Literal(comment, lang="en")))
        g.add((uri, RDFS.isDefinedBy, ontology))
        if domain is not None:
            g.add((uri, RDFS.domain, domain))
        if range_ is not None:
            g.add((uri, RDFS.range, range_))
        if subprop is not None:
            g.add((uri, RDFS.subPropertyOf, subprop))

    add_obj_prop(INTEGMET.analysisGroup, "analysis group", "Links a study to an analysis-group resource representing a study file or file grouping.", INTEGMET.Study, INTEGMET.AnalysisGroup)
    add_obj_prop(INTEGMET.categoryInfo, "category info", "IntegMet-curated category metadata assigned to a study based on cited source information.", INTEGMET.Study, INTEGMET.StudyCategoryClassification, DCAT.theme)
    add_data_prop(INTEGMET.categoryBranch, "category branch", "Top-level branch in the IntegMet study category hierarchy.", INTEGMET.StudyCategoryClassification, RDF.langString)
    add_data_prop(INTEGMET.category, "category", "Middle-level category in the IntegMet study category hierarchy.", INTEGMET.StudyCategoryClassification, RDF.langString)
    add_data_prop(INTEGMET.subcategory, "subcategory", "Lowest-level category in the IntegMet study category hierarchy.", INTEGMET.StudyCategoryClassification, RDF.langString)

    add_data_prop(INTEGMET.derivedAbstract, "derived abstract", "A study summary generated by IntegMet from abstract and description metadata in cited source resources.", INTEGMET.Study, RDFS.Literal, SCHEMA.abstract)
    add_data_prop(INTEGMET.derivedDescription, "derived description", "A study description generated by IntegMet from abstract and description metadata in cited source resources.", INTEGMET.Study, RDFS.Literal, SCHEMA.description)
    add_data_prop(INTEGMET.observations, "observations", "Observation summary curated for an IntegMet study.", INTEGMET.Study, RDFS.Literal)
    add_data_prop(INTEGMET.findings, "findings", "Finding summary curated for an IntegMet study.", INTEGMET.Study, RDFS.Literal)
    add_data_prop(INTEGMET.graphGroup, "graph group", "A coarse study grouping label used within IntegMet for graph construction and downstream grouping workflows.", INTEGMET.Study, RDF.langString)
    add_data_prop(INTEGMET.hasRetentionIndex, "has retention index", "Boolean flag indicating that the study includes retention index information.", INTEGMET.Study, XSD.boolean)
    add_data_prop(INTEGMET.isLipidomics, "is lipidomics", "Boolean flag indicating that the study contains lipidomics-related source data.", INTEGMET.Study, XSD.boolean)

    add_data_prop(INTEGMET.unresolvedTaxonomy, "unresolved taxonomy", "A taxonomy string captured from a cited source when it could not be normalized to an NCBI Taxonomy identifier.", INTEGMET.SourceDerivedOrganismAnnotationSet, XSD.string)
    add_obj_prop(INTEGMET.organismAnnotation, "organism annotation", "Relates an IntegMet study to a source-derived organism annotation set node that captures one or more organism values together with provenance to the cited source project.", INTEGMET.Study, INTEGMET.SourceDerivedOrganismAnnotationSet)
    add_obj_prop(INTEGMET.organism, "organism", "Relates a source-derived organism annotation set to a normalized organism resource, typically an NCBI Taxonomy identifier.", INTEGMET.SourceDerivedOrganismAnnotationSet, RDFS.Resource)

    add_obj_prop(INTEGMET.hasAnnotatedMeSHTerm, "has annotated MeSH term", "Relates an IntegMet study to a MeSH term assigned by annotation or downstream analysis of the source project metadata.", INTEGMET.Study, RDFS.Resource, DC.subject)
    add_obj_prop(INTEGMET.hasAnnotatedGOTerm, "has annotated GO term", "Relates an IntegMet study to a Gene Ontology term assigned by annotation or downstream analysis of the source project metadata.", INTEGMET.Study, RDFS.Resource, DC.subject)
    add_obj_prop(INTEGMET.hasAnnotatedNCBIGene, "has annotated NCBI Gene", "Relates an IntegMet study to an NCBI Gene resource assigned by annotation or downstream analysis of the source project metadata.", INTEGMET.Study, RDFS.Resource, DC.subject)
    add_obj_prop(INTEGMET.hasAnnotatedOMIMEntry, "has annotated OMIM entry", "Relates an IntegMet study to an OMIM entry assigned by annotation or downstream analysis of the source project metadata.", INTEGMET.Study, RDFS.Resource, DC.subject)

    return g


def build_rdf(input_json: str, output_base: str) -> None:
    graph_json = load_graph_json(input_json)
    nodes = graph_json["nodes"]
    relationships = graph_json["relationships"]

    node_by_element_id = {node["elementId"]: node for node in nodes if "elementId" in node}

    rels_by_start = defaultdict(list)
    rels_by_end = defaultdict(list)
    for rel in relationships:
        start_id = rel.get("startElementId")
        end_id = rel.get("endElementId")
        if start_id:
            rels_by_start[start_id].append(rel)
        if end_id:
            rels_by_end[end_id].append(rel)

    rdf_graph = Graph()
    bind_prefixes(rdf_graph)

    study_count = 0

    for node in nodes:
        if "Study" not in node.get("labels", []):
            continue

        props = node.get("properties", {})
        study_value, study_value_source = get_study_candidate_value(props)
        source_ns_name, source_study_id = get_study_source_namespace_and_id(study_value)
        if source_ns_name is None:
            continue

        study_id = source_study_id
        subject = INTEGMET_STUDY[safe_name(study_id)]
        study_count += 1

        rdf_graph.add((subject, RDF.type, INTEGMET.Study))
        rdf_graph.add((subject, RDF.type, DCAT.Dataset))
        rdf_graph.add((subject, DC.identifier, Literal(str(study_id), datatype=XSD.string)))
        rdf_graph.add((subject, RDFS.label, Literal(str(study_id), lang="en")))

        if source_ns_name == "metabolights":
            source_uri = URIRef(str(METABOLIGHTS) + study_id)
        elif source_ns_name == "mwstudy":
            source_uri = URIRef(str(MWSTUDY) + study_id)
        else:
            source_uri = None

        if source_uri is not None:
            rdf_graph.add((subject, PROV.wasDerivedFrom, source_uri))
            rdf_graph.add((subject, DC.source, source_uri))

        add_category_info(rdf_graph, subject, study_id, props)

        if props.get("summary_by_llm") not in (None, ""):
            add_en_literal(rdf_graph, subject, INTEGMET.derivedAbstract, props["summary_by_llm"])
        if props.get("observations_by_llm") not in (None, ""):
            add_en_literal(rdf_graph, subject, INTEGMET.observations, props["observations_by_llm"])
        if props.get("findings_by_llm") not in (None, ""):
            add_en_literal(rdf_graph, subject, INTEGMET.findings, props["findings_by_llm"])
        if props.get("graph_group") not in (None, ""):
            add_en_literal(rdf_graph, subject, INTEGMET.graphGroup, props["graph_group"])

        seen_annotation_objects = set()
        has_retention_index = False
        is_lipidomics = False
        species_numeric = set()
        species_unresolved = set()

        for rel in rels_by_start.get(node["elementId"], []):
            rel_type = rel.get("type")
            end_node = node_by_element_id.get(rel.get("endElementId"))
            if not rel_type:
                continue

            end_props = end_node.get("properties", {}) if end_node else {}

            if rel_type == "HAS_DATA":
                candidate_values = []
                if "Nodeid" in end_props:
                    candidate_values.append(end_props["Nodeid"])
                if "id" in end_props:
                    candidate_values.append(end_props["id"])
                if rel.get("endIdentifier") is not None:
                    candidate_values.append(rel.get("endIdentifier"))

                for raw in candidate_values:
                    text = normalize_text(raw).lower()
                    if "retentionindex" in text:
                        has_retention_index = True
                    if "lipidomics" in text:
                        is_lipidomics = True
                continue

            if rel_type == "Metadata_MeSH":
                if "identifier" in end_props:
                    dedup_key = add_annotated_term_from_mesh_identifier(
                        rdf_graph, subject, end_props["identifier"]
                    )
                    if dedup_key:
                        seen_annotation_objects.add(dedup_key)

            if rel_type == "HAS_GO_ANNOTATION" and "id" in end_props:
                dedup_key = add_annotated_go_term(
                    rdf_graph, subject, end_props["id"]
                )
                if dedup_key:
                    seen_annotation_objects.add(dedup_key)

            if rel_type == "Metadata_Species" and "Nodeid" in end_props:
                text_value = normalize_text(end_props["Nodeid"])
                if text_value.startswith("TaxonId:"):
                    suffix = text_value[len("TaxonId:"):].strip()
                    if suffix.isdigit():
                        species_numeric.add(suffix)
                    elif text_value:
                        species_unresolved.add(text_value)
                elif text_value.startswith("taxonomy:"):
                    suffix = text_value[len("taxonomy:"):].strip()
                    if suffix.isdigit():
                        species_numeric.add(suffix)
                    elif text_value:
                        species_unresolved.add(text_value)
                elif text_value.isdigit():
                    species_numeric.add(text_value)
                elif text_value:
                    species_unresolved.add(text_value)

        if has_retention_index:
            rdf_graph.add((subject, INTEGMET.hasRetentionIndex, Literal(True, datatype=XSD.boolean)))
        if is_lipidomics:
            rdf_graph.add((subject, INTEGMET.isLipidomics, Literal(True, datatype=XSD.boolean)))

        if species_numeric or species_unresolved:
            organism_set = ORGANISM_ANNOTATION_RES[iri_fragment(f"{study_id}_taxonomy")]
            rdf_graph.add((subject, INTEGMET.organismAnnotation, organism_set))
            rdf_graph.add((organism_set, RDF.type, INTEGMET.SourceDerivedOrganismAnnotationSet))
            rdf_graph.add((organism_set, RDFS.label, Literal(f"{study_id} organism annotation set", lang="en")))
            if source_uri is not None:
                rdf_graph.add((organism_set, PROV.hadPrimarySource, source_uri))
                rdf_graph.add((organism_set, DC.source, source_uri))
            for suffix in sorted(species_numeric):
                rdf_graph.add((organism_set, INTEGMET.organism, URIRef(str(TAXONOMY) + suffix)))
            for raw in sorted(species_unresolved):
                rdf_graph.add((organism_set, INTEGMET.unresolvedTaxonomy, Literal(raw, datatype=XSD.string)))

        # Incoming AnalyticsGroup nodes
        for rel in rels_by_end.get(node["elementId"], []):
            if rel.get("type") != ANALYTICS_GROUP_TO_STUDY_REL:
                continue

            analytics_node = node_by_element_id.get(rel.get("startElementId"))
            if not analytics_node or ANALYTICS_GROUP_LABEL not in analytics_node.get("labels", []):
                continue

            analytics_props = analytics_node.get("properties", {})
            analytics_identifier = analytics_node.get("identifier")
            if analytics_identifier is None:
                analytics_identifier = analytics_props.get("identifier")

            ag_key = analytics_identifier if analytics_identifier not in (None, "") else analytics_node.get("elementId")
            b = ANALYSIS_GROUP_RES[iri_fragment(str(ag_key))]
            rdf_graph.add((subject, INTEGMET.analysisGroup, b))
            rdf_graph.add((b, RDF.type, INTEGMET.AnalysisGroup))

            if analytics_identifier not in (None, ""):
                rdf_graph.add((b, DC.identifier, Literal(str(analytics_identifier), datatype=XSD.string)))
                rdf_graph.add((b, RDFS.label, Literal(str(analytics_identifier), lang="en")))

            if analytics_props.get("FileName") not in (None, ""):
                rdf_graph.add((b, NFO.fileName, Literal(str(analytics_props["FileName"]), datatype=XSD.string)))

            seen_analysis_types = set()
            for ag_rel in rels_by_start.get(analytics_node["elementId"], []):
                if ag_rel.get("type") != ANALYTICS_TYPE_REL:
                    continue

                analysis_type_node = node_by_element_id.get(ag_rel.get("endElementId"))
                if not analysis_type_node or "AnalysisType" not in analysis_type_node.get("labels", []):
                    continue

                analysis_type_value = analysis_type_node.get("properties", {}).get("AnalysisType")
                analysis_type_text = normalize_text(analysis_type_value)
                if not analysis_type_text or analysis_type_text in seen_analysis_types:
                    continue
                seen_analysis_types.add(analysis_type_text)
                add_measurement_technique(rdf_graph, b, analysis_type_text)

    output_base = str(output_base)
    if output_base.lower().endswith(".ttl"):
        output_base = output_base[:-4]
    elif output_base.lower().endswith(".nt"):
        output_base = output_base[:-3]
    elif output_base.lower().endswith(".jsonld"):
        output_base = output_base[:-7]

    ttl_path = output_base + ".ttl"
    nt_path = output_base + ".nt"
    jsonld_path = output_base + ".jsonld"
    ontology_ttl_path = output_base + "_ontology.ttl"

    rdf_graph.serialize(destination=ttl_path, format="turtle")
    normalize_ttl_prefixes(ttl_path)
    rdf_graph.serialize(destination=nt_path, format="nt")
    rdf_graph.serialize(destination=jsonld_path, format="json-ld", indent=2, auto_compact=False)

    ontology_graph = build_ontology_graph()
    ontology_graph.serialize(destination=ontology_ttl_path, format="turtle")
    normalize_ttl_prefixes(ontology_ttl_path)

    print(f"Done: {study_count} Study subjects written to {ttl_path}, {nt_path}, {jsonld_path}, and ontology {ontology_ttl_path}")


def main():
    # if len(sys.argv) > 2:
    #     print("Usage: python study_json_to_rdf_with_ontology.py [output_base]")
    #     sys.exit(1)

    # output_base = sys.argv[1] if len(sys.argv) == 2 else DEFAULT_OUTPUT_BASE
    build_rdf("neo4j_query_table_data_2026-4-3.json", "integmet_study_rdf")


if __name__ == "__main__":
    main()
