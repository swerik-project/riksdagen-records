#!/usr/bin/env python3
"""
Temporary local DCAT generator for repository info YAML.

This file is intentionally written as a small, self-contained module so it can
be copied into pyriksdagen. When pyriksdagen provides
`pyriksdagen.repository_info.write_dcat_rdf`, delete this file and import that
shared function instead. The guard test in test.repository_info will fail when
the pyriksdagen function exists.
"""

from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET

import yaml


RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DCAT_NS = "http://www.w3.org/ns/dcat#"
DCT_NS = "http://purl.org/dc/terms/"
FOAF_NS = "http://xmlns.com/foaf/0.1/"
VCARD_NS = "http://www.w3.org/2006/vcard/ns#"
XML_NS = "http://www.w3.org/XML/1998/namespace"
DATA_THEME_VOCABULARY = "http://publications.europa.eu/resource/authority/data-theme"

NS = {
    "rdf": RDF_NS,
    "dcat": DCAT_NS,
    "dct": DCT_NS,
    "foaf": FOAF_NS,
    "vcard": VCARD_NS,
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def qname(namespace, tag):
    return f"{{{namespace}}}{tag}"


def lang_text(parent, namespace, tag, values):
    for language, text in values.items():
        if text == "":
            continue
        element = ET.SubElement(parent, qname(namespace, tag))
        element.set(qname(XML_NS, "lang"), language)
        element.text = text


def text_element(parent, namespace, tag, text):
    if text == "":
        return None
    element = ET.SubElement(parent, qname(namespace, tag))
    element.text = str(text)
    return element


def resource_element(parent, namespace, tag, resource):
    if resource == "":
        return None
    element = ET.SubElement(parent, qname(namespace, tag))
    element.set(qname(RDF_NS, "resource"), resource)
    return element


def load_repository_info(info_path):
    with Path(info_path).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def repository_info_to_dcat_rdf(info):
    repository = info["repository"]
    dataset = info["dataset"]
    publisher = info["publisher"]
    contact = info["contact"]
    documentation = info.get("documentation", {})
    citation = info.get("citation", {})
    relations = info.get("relations", {})

    root = ET.Element(qname(RDF_NS, "RDF"))

    catalog_uri = f"{repository['url']}#catalog"
    catalog_element = ET.SubElement(root, qname(DCAT_NS, "Catalog"))
    catalog_element.set(qname(RDF_NS, "about"), catalog_uri)
    catalog_titles = {
        language: f"{title} metadata catalog"
        for language, title in dataset.get("title", {}).items()
    }
    catalog_descriptions = {
        language: f"DCAT-AP-SE metadata catalog for {title}."
        for language, title in dataset.get("title", {}).items()
    }
    lang_text(catalog_element, DCT_NS, "title", catalog_titles)
    lang_text(catalog_element, DCT_NS, "description", catalog_descriptions)
    resource_element(catalog_element, DCT_NS, "publisher", publisher.get("url", ""))
    resource_element(catalog_element, DCAT_NS, "dataset", repository["url"])
    resource_element(catalog_element, DCAT_NS, "themeTaxonomy", DATA_THEME_VOCABULARY)

    dataset_element = ET.SubElement(root, qname(DCAT_NS, "Dataset"))
    dataset_element.set(qname(RDF_NS, "about"), repository["url"])
    lang_text(dataset_element, DCT_NS, "title", dataset.get("title", {}))
    lang_text(dataset_element, DCT_NS, "description", dataset.get("description", {}))
    text_element(dataset_element, DCT_NS, "identifier", dataset.get("identifier", ""))
    text_element(dataset_element, DCT_NS, "type", dataset.get("type", ""))
    resource_element(dataset_element, DCAT_NS, "landingPage", dataset.get("landing_page_url", ""))
    resource_element(dataset_element, DCT_NS, "license", dataset.get("license", ""))
    text_element(dataset_element, DCT_NS, "temporal", dataset.get("temporal_coverage", ""))

    for language in dataset.get("languages", []):
        text_element(dataset_element, DCT_NS, "language", language)

    for language, keywords in dataset.get("keywords", {}).items():
        for keyword in keywords:
            keyword_element = text_element(dataset_element, DCAT_NS, "keyword", keyword)
            if keyword_element is not None:
                keyword_element.set(qname(XML_NS, "lang"), language)

    for theme in dataset.get("themes", []):
        resource_element(dataset_element, DCAT_NS, "theme", theme)

    resource_element(dataset_element, DCT_NS, "publisher", publisher.get("url", ""))
    resource_element(dataset_element, DCAT_NS, "contactPoint", contact.get("url", ""))
    for documentation_url in documentation.values():
        resource_element(dataset_element, DCT_NS, "isReferencedBy", documentation_url)
    resource_element(dataset_element, DCT_NS, "isReferencedBy", citation.get("cff_url", ""))
    for related_repository in relations.get("related_repositories", []):
        resource_element(dataset_element, DCT_NS, "relation", related_repository)

    publisher_uri = publisher.get("url", "")
    if publisher_uri:
        publisher_element = ET.SubElement(root, qname(FOAF_NS, "Agent"))
        publisher_element.set(qname(RDF_NS, "about"), publisher_uri)
        lang_text(publisher_element, FOAF_NS, "name", publisher.get("name", {}))

    contact_uri = contact.get("url", "")
    if contact_uri:
        contact_element = ET.SubElement(root, qname(VCARD_NS, "Organization"))
        contact_element.set(qname(RDF_NS, "about"), contact_uri)
        text_element(contact_element, VCARD_NS, "fn", contact.get("name", ""))

    for distribution in info.get("distributions", []):
        distribution_uri = distribution.get("download_url", "")
        if distribution_uri == "":
            distribution_uri = f"{repository['url']}#distribution-{quote(distribution['name'])}"
        resource_element(dataset_element, DCAT_NS, "distribution", distribution_uri)
        distribution_element = ET.SubElement(root, qname(DCAT_NS, "Distribution"))
        distribution_element.set(qname(RDF_NS, "about"), distribution_uri)
        text_element(distribution_element, DCT_NS, "title", distribution.get("name", ""))
        resource_element(distribution_element, DCAT_NS, "downloadURL", distribution.get("download_url", ""))
        text_element(distribution_element, DCAT_NS, "mediaType", distribution.get("media_type", ""))
        text_element(distribution_element, DCT_NS, "format", distribution.get("format", ""))

    return ET.ElementTree(root)


def write_dcat_rdf(info_path, output_path):
    info = load_repository_info(info_path)
    tree = repository_info_to_dcat_rdf(info)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path
