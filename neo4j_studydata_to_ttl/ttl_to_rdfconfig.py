#!/usr/bin/env python3
from __future__ import annotations

import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from rdflib import BNode, Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef

# -----------------------------------------------------------------------------
# User settings
# Edit these paths to match your environment.
# -----------------------------------------------------------------------------
ONTOLOGY_TTL_PATH = Path("integmet_study_rdf_ontology.ttl")
DATA_TTL_PATH = Path("integmet_study_rdf.ttl")
OUTPUT_DIR = Path("integMET")
EXAMPLES_PER_CLASS = 1

DC = Namespace("http://purl.org/dc/elements/1.1/")
DCT = Namespace("http://purl.org/dc/terms/")
PROV = Namespace("http://www.w3.org/ns/prov#")
XSD_BOOLEAN = URIRef("http://www.w3.org/2001/XMLSchema#boolean")
XSD_INTEGER = URIRef("http://www.w3.org/2001/XMLSchema#integer")
XSD_DECIMAL = URIRef("http://www.w3.org/2001/XMLSchema#decimal")
XSD_DOUBLE = URIRef("http://www.w3.org/2001/XMLSchema#double")
XSD_FLOAT = URIRef("http://www.w3.org/2001/XMLSchema#float")
XSD_STRING = URIRef("http://www.w3.org/2001/XMLSchema#string")


@dataclass
class PropertyInfo:
    predicate: URIRef
    counts: List[int]
    values: List[object]
    target_class: Optional[URIRef]


@dataclass
class ModelProperty:
    predicate: URIRef
    cardinality_marker: str
    object_name: str
    example_value: Union[object, str]
    target_class: Optional[URIRef]
    counts: List[int]


@dataclass
class SubjectModel:
    name: str
    class_uri: URIRef
    example_instances: List[URIRef]
    rdf_types: List[URIRef]
    properties: List[ModelProperty]


class TTLToRDFConfig:
    def __init__(self, ontology_path: Path, data_path: Path, examples_per_class: int = 3):
        self.ontology_path = ontology_path
        self.data_path = data_path
        self.examples_per_class = examples_per_class

        self.ontology = Graph()
        self.ontology.parse(str(ontology_path), format="turtle")

        self.data = Graph()
        self.data.parse(str(data_path), format="turtle")

        self.graph = Graph()
        for prefix, ns in self.ontology.namespaces():
            self.graph.bind(prefix, ns)
        for prefix, ns in self.data.namespaces():
            self.graph.bind(prefix, ns)
        for triple in self.ontology:
            self.graph.add(triple)
        for triple in self.data:
            self.graph.add(triple)

        self.prefix_map = self._build_prefix_map()
        self.class_uris = self._discover_classes()
        self.subject_names = {cls: self._subject_name_for_class(cls) for cls in self.class_uris}
        self.global_object_names: set[str] = set()
        self.subject_models: Optional[List[SubjectModel]] = None

    def _build_prefix_map(self) -> OrderedDict[str, str]:
        """Preserve prefixes explicitly declared in the source TTL files.

        The data TTL is preferred over the ontology TTL so that instance-side aliases
        win when the same namespace URI is bound to multiple prefixes.
        """
        prefix_re = re.compile(r"^@prefix\s+([^:\s]+):\s+<([^>]+)>\s*\.")
        ordered: OrderedDict[str, str] = OrderedDict()
        namespace_to_prefix: Dict[str, str] = {}

        for path in (self.data_path, self.ontology_path):
            for line in path.read_text(encoding="utf-8").splitlines():
                m = prefix_re.match(line.strip())
                if not m:
                    continue
                prefix, uri = m.group(1), m.group(2)
                if uri in namespace_to_prefix:
                    continue
                if prefix not in ordered:
                    ordered[prefix] = uri
                    namespace_to_prefix[uri] = prefix

        for prefix, ns in self.graph.namespaces():
            prefix = str(prefix)
            uri = str(ns)
            if uri in namespace_to_prefix:
                continue
            if prefix not in ordered:
                ordered[prefix] = uri
                namespace_to_prefix[uri] = prefix
        return ordered

    def _discover_classes(self) -> List[URIRef]:
        classes = set(self.ontology.subjects(RDF.type, OWL.Class))
        ontology_class_namespaces = {
            str(c).rsplit("#", 1)[0] + "#" if "#" in str(c) else str(c).rsplit("/", 1)[0] + "/"
            for c in classes
        }
        for _, _, cls in self.data.triples((None, RDF.type, None)):
            if isinstance(cls, URIRef) and any(str(cls).startswith(ns) for ns in ontology_class_namespaces):
                classes.add(cls)
        return sorted(classes, key=lambda u: self.qname(u))

    def qname(self, node: URIRef) -> str:
        uri = str(node)
        best_prefix = None
        best_ns = ""
        for prefix, ns in self.prefix_map.items():
            if uri.startswith(ns) and len(ns) > len(best_ns):
                best_prefix = prefix
                best_ns = ns
        if best_prefix is not None:
            return f"{best_prefix}:{uri[len(best_ns):]}"
        return f"<{uri}>"

    @staticmethod
    def _local_name(uri: URIRef) -> str:
        text = str(uri)
        if "#" in text:
            return text.rsplit("#", 1)[1]
        if "/" in text:
            return text.rsplit("/", 1)[1]
        if ":" in text:
            return text.rsplit(":", 1)[1]
        return text

    @staticmethod
    def to_snake(text: str) -> str:
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
        text = re.sub(r"[^A-Za-z0-9]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text.lower() or "value"

    @staticmethod
    def to_camel(text: str) -> str:
        text = re.sub(r"[^A-Za-z0-9]+", " ", text)
        parts = [p for p in text.split() if p]
        if not parts:
            return "Subject"
        return "".join(p[:1].upper() + p[1:] for p in parts)

    @staticmethod
    def humanize_identifier(text: str) -> str:
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return "value"
        return text[:1].upper() + text[1:]

    @staticmethod
    def ensure_sentence(text: str) -> str:
        text = text.strip()
        if not text:
            return text
        if text[-1] not in ".!?":
            return text + "."
        return text

    def _preferred_literal(self, values: Iterable[Literal]) -> Optional[str]:
        literals = [v for v in values if isinstance(v, Literal)]
        if not literals:
            return None

        def lang_rank(lit: Literal) -> Tuple[int, str]:
            lang = lit.language or ""
            if lang == "en":
                return (0, str(lit))
            if not lang:
                return (1, str(lit))
            return (2, str(lit))

        return str(sorted(literals, key=lang_rank)[0]).strip()

    def label_for(self, uri: URIRef) -> Optional[str]:
        return self._preferred_literal(self.ontology.objects(uri, RDFS.label)) or self._preferred_literal(
            self.graph.objects(uri, RDFS.label)
        )

    def comment_for(self, uri: URIRef) -> Optional[str]:
        return self._preferred_literal(self.ontology.objects(uri, RDFS.comment)) or self._preferred_literal(
            self.graph.objects(uri, RDFS.comment)
        )

    def _subject_name_for_class(self, cls: URIRef) -> str:
        return self.to_camel(self._local_name(cls))

    def _instances_of(self, cls: URIRef) -> List[URIRef]:
        instances = {s for s in self.data.subjects(RDF.type, cls) if isinstance(s, URIRef)}
        return sorted(instances, key=self.qname)

    def _predicates_for_instances(self, instances: Sequence[URIRef]) -> List[URIRef]:
        preds = set()
        for subject in instances:
            for predicate, _ in self.data.predicate_objects(subject):
                if predicate != RDF.type:
                    preds.add(predicate)
        priority = {
            str(RDFS.label): 1,
            str(DC.identifier): 2,
            str(DCT.identifier): 2,
            str(DC.source): 3,
            str(PROV.wasDerivedFrom): 4,
        }
        return sorted(preds, key=lambda p: (priority.get(str(p), 100), self.qname(p)))

    def _infer_target_class(self, objects: Sequence[object]) -> Optional[URIRef]:
        typed_classes: List[URIRef] = []
        for obj in objects:
            if not isinstance(obj, URIRef):
                continue
            classes = [class_uri for class_uri in self.data.objects(obj, RDF.type) if class_uri in self.class_uris]
            typed_classes.extend(classes)
        if not typed_classes:
            return None
        counts = defaultdict(int)
        for class_uri in typed_classes:
            counts[class_uri] += 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], self.qname(kv[0])))[0][0]

    @staticmethod
    def _infer_cardinality(counts: Sequence[int]) -> str:
        if not counts:
            return "?"
        min_count = min(counts)
        max_count = max(counts)
        if min_count == max_count:
            if min_count == 0:
                return "?"
            if min_count == 1:
                return ""
            return f"{{{min_count}}}"
        if min_count == 0 and max_count == 1:
            return "?"
        if min_count == 0 and max_count > 1:
            return "*"
        if min_count >= 1 and max_count > 1:
            if min_count == 1:
                return "+"
            return f"{{{min_count},{max_count}}}"
        return ""

    def _property_info(self, instances: Sequence[URIRef], predicate: URIRef) -> PropertyInfo:
        counts = []
        values: List[object] = []
        for s in instances:
            objs = list(self.data.objects(s, predicate))
            counts.append(len(objs))
            values.extend(objs)
        return PropertyInfo(
            predicate=predicate,
            counts=counts,
            values=values,
            target_class=self._infer_target_class(values),
        )

    def _format_literal(self, lit: Literal) -> str:
        value = str(lit)

        # Suppress language tags such as @en and plain string datatype markers
        # such as ^^xsd:string when writing model.yaml examples.
        if lit.language or lit.datatype == XSD_STRING:
            if "\n" in value:
                return "|\n" + "\n".join(f"        {line}" for line in value.splitlines())
            escaped = value.replace('"', '\\"')
            return f'"{escaped}"'

        if lit.datatype:
            dtype_qname = self.qname(lit.datatype)
            if lit.datatype in {XSD_BOOLEAN, XSD_INTEGER, XSD_DECIMAL, XSD_DOUBLE, XSD_FLOAT}:
                return value
            escaped = value.replace('"', '\\"')
            return f'"{escaped}"^^{dtype_qname}'

        if "\n" in value:
            return "|\n" + "\n".join(f"        {line}" for line in value.splitlines())
        if re.fullmatch(r"-?\d+", value) or re.fullmatch(r"-?\d+\.\d+", value):
            return value
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'

    def _format_node(self, node: object) -> str:
        if isinstance(node, Literal):
            return self._format_literal(node)
        if isinstance(node, URIRef):
            return self.qname(node)
        if isinstance(node, BNode):
            return "[]"
        return '""'

    def _predicate_label(self, predicate: URIRef) -> str:
        return self.label_for(predicate) or self.humanize_identifier(self._local_name(predicate)).lower()

    def _candidate_object_name(
        self, subject_name: str, predicate: URIRef, target_class: Optional[URIRef], sample_value: object
    ) -> str:
        subj = self.to_snake(subject_name)
        pred_local = self.to_snake(self._local_name(predicate))

        if predicate == RDFS.label:
            base = f"{subj}_label"
        elif predicate in {DC.identifier, DCT.identifier}:
            base = f"{subj}_id"
        elif target_class is not None:
            base = self.to_snake(self.subject_names[target_class])
        else:
            pred_label = self._predicate_label(predicate)
            pred_snake = self.to_snake(pred_label)
            if isinstance(sample_value, URIRef):
                base = pred_snake or f"{pred_local}_resource"
            elif isinstance(sample_value, Literal) and sample_value.datatype == XSD_BOOLEAN:
                base = pred_snake if pred_snake.endswith("flag") else f"{pred_snake}_flag"
            else:
                if pred_snake in {"label", "identifier", "id"}:
                    base = f"{subj}_{pred_snake}"
                else:
                    base = pred_snake or f"{subj}_{pred_local}"

        candidate = base
        i = 2
        while candidate in self.global_object_names:
            candidate = f"{base}_{i}"
            i += 1
        self.global_object_names.add(candidate)
        return candidate

    def _choose_example_value(self, prop: PropertyInfo) -> Union[object, str]:
        if prop.target_class is not None:
            return self.subject_names[prop.target_class]
        non_blank = [v for v in prop.values]
        if not non_blank:
            return Literal("")

        def sort_key(v: object) -> Tuple[int, str]:
            if isinstance(v, Literal):
                return (0, str(v))
            if isinstance(v, URIRef):
                return (1, self.qname(v))
            return (2, str(v))

        return sorted(non_blank, key=sort_key)[0]

    def build_subject_models(self) -> List[SubjectModel]:
        if self.subject_models is not None:
            return self.subject_models

        self.global_object_names = set()
        models: List[SubjectModel] = []

        for cls in self.class_uris:
            instances = self._instances_of(cls)
            if not instances:
                continue

            subject_name = self.subject_names[cls]
            sample_instances = instances[: self.examples_per_class]

            sample_types = set()
            for inst in sample_instances:
                sample_types.update({o for o in self.data.objects(inst, RDF.type) if isinstance(o, URIRef)})
            ordered_types = sorted(sample_types, key=self.qname)

            properties: List[ModelProperty] = []
            for predicate in self._predicates_for_instances(instances):
                prop = self._property_info(instances, predicate)
                marker = self._infer_cardinality(prop.counts)
                example_value = self._choose_example_value(prop)
                object_name = self._candidate_object_name(subject_name, predicate, prop.target_class, example_value)
                properties.append(
                    ModelProperty(
                        predicate=predicate,
                        cardinality_marker=marker,
                        object_name=object_name,
                        example_value=example_value,
                        target_class=prop.target_class,
                        counts=prop.counts,
                    )
                )

            models.append(
                SubjectModel(
                    name=subject_name,
                    class_uri=cls,
                    example_instances=sample_instances,
                    rdf_types=ordered_types,
                    properties=properties,
                )
            )

        self.subject_models = models
        return models

    def generate_prefix_yaml(self) -> str:
        lines = []
        for prefix, ns in self.prefix_map.items():
            lines.append(f"{prefix}: <{ns}>")
        return "\n".join(lines) + "\n"

    def generate_model_yaml(self) -> str:
        models = self.build_subject_models()
        lines = [
            "# Auto-generated from TTL files.",
            "# Cardinality markers are inferred from observed instance counts in the supplied data TTL.",
            "# Review subject/object names before using the file in production.",
            "",
        ]

        for model in models:
            header_examples = " ".join(self.qname(s) for s in model.example_instances)
            header = f"- {model.name}{(' ' + header_examples) if header_examples else ''}:"
            lines.append(header)

            if model.rdf_types:
                if len(model.rdf_types) == 1:
                    lines.append(f"  - a: {self.qname(model.rdf_types[0])}")
                else:
                    lines.append("  - a:")
                    for rdf_type in model.rdf_types:
                        lines.append(f"    - {self.qname(rdf_type)}")

            for prop in model.properties:
                pred_text = self.qname(prop.predicate) + prop.cardinality_marker
                example_value = prop.example_value
                example_text = (
                    example_value
                    if isinstance(example_value, str) and prop.target_class is not None
                    else self._format_node(example_value)
                )
                lines.append(f"  - {pred_text}:")
                if isinstance(example_text, str) and example_text.startswith("|\n"):
                    lines.append(f"    - {prop.object_name}: {example_text.splitlines()[0]}")
                    lines.extend(example_text.splitlines()[1:])
                else:
                    lines.append(f"    - {prop.object_name}: {example_text}")

            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _dataset_name(self) -> str:
        stem = self.data_path.stem
        stem = stem.replace("_", " ").replace("-", " ").strip()
        return self.humanize_identifier(stem)

    def _dataset_description(self) -> str:
        class_labels = [self.label_for(model.class_uri) or self.humanize_identifier(model.name) for model in self.build_subject_models()]
        if class_labels:
            joined = ", ".join(class_labels)
            text = (
                f"Auto-generated dataset descriptions derived from {self.data_path.name} and "
                f"{self.ontology_path.name}. Main modeled subjects include {joined}."
            )
        else:
            text = f"Auto-generated dataset descriptions derived from {self.data_path.name} and {self.ontology_path.name}."
        return self.ensure_sentence(text)

    def _subject_description(self, model: SubjectModel) -> str:
        return self.ensure_sentence(
            self.comment_for(model.class_uri)
            or self.label_for(model.class_uri)
            or f"Subject representing {self.humanize_identifier(model.name).lower()}"
        )

    def _object_description(self, model: SubjectModel, prop: ModelProperty) -> Optional[str]:
        subject_label = self.label_for(model.class_uri) or self.humanize_identifier(model.name).lower()
        predicate_label = self._predicate_label(prop.predicate)
        predicate_comment = self.comment_for(prop.predicate)

        if prop.target_class is not None:
            target_name = self.subject_names[prop.target_class]
            target_label = self.label_for(prop.target_class) or self.humanize_identifier(target_name).lower()
            base = f"Reference from {subject_label} to {target_label} via {predicate_label}."
            if predicate_comment:
                return self.ensure_sentence(predicate_comment)
            return self.ensure_sentence(base)

        if prop.predicate == RDFS.label:
            return self.ensure_sentence(f"Human-readable label for {subject_label}.")
        if prop.predicate in {DC.identifier, DCT.identifier}:
            return self.ensure_sentence(f"Identifier for {subject_label}.")
        if predicate_comment:
            return self.ensure_sentence(predicate_comment)
        return None

    def generate_description_yaml(self) -> str:
        models = self.build_subject_models()
        lines = [
            "# Auto-generated from TTL files.",
            "dataset:",
            f"  name: \"{self._dataset_name()}\"",
            f"  description: \"{self._dataset_description().replace('\\\"', '\\\\\\\"')}\"",
            "variables:",
        ]

        for model in models:
            subject_desc = self._subject_description(model).replace('"', '\\"')
            lines.append(f"  {model.name}: \"{subject_desc}\"")
            for prop in model.properties:
                object_desc = self._object_description(model, prop)
                if not object_desc:
                    continue
                object_desc = object_desc.replace('"', '\\"')
                lines.append(f"  {prop.object_name}: \"{object_desc}\"")

        return "\n".join(lines) + "\n"


def main() -> None:
    generator = TTLToRDFConfig(ONTOLOGY_TTL_PATH, DATA_TTL_PATH, examples_per_class=EXAMPLES_PER_CLASS)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    outputs = {
        "prefix.yaml": generator.generate_prefix_yaml(),
        "model.yaml": generator.generate_model_yaml(),
        "description.yaml": generator.generate_description_yaml(),
    }

    for filename, content in outputs.items():
        path = OUTPUT_DIR / filename
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
