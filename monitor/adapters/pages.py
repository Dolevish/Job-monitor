"""Shared parsing for public careers pages. Empty/unrecognised HTML fails closed."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..http import html_to_text


def soup(page):
    return BeautifulSoup(page, "html.parser")


def text(node):
    return node.get_text(" ", strip=True) if node else ""


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def description(http, board, job):
    doc = soup(http.get_text(job.url))
    selector = job.extra.get("detail_selector", "main, article, [role=main]")
    node = doc.select_one(selector)
    if node is None:
        raise ValueError("Job page: expected full description container is missing")
    # Never use navigation, related jobs, or site footers as qualification evidence.
    for el in node.select("script, style, nav, footer, form, .related-jobs, .similar-jobs"):
        el.decompose()
    body = html_to_text(str(node))
    if len(body) < 80 or not re.search(r"requirement|qualification|responsibilit|experience|דרישות|ניסיון|נסיון|תיאור", body, re.I):
        raise ValueError("Job page: no usable job description")
    job.description = body


def unique_extend(out, batch, seen):
    if batch and all(j.job_id in seen for j in batch):
        raise ValueError("Careers site repeated a page; refusing incomplete results")
    for job in batch:
        if job.job_id not in seen:
            seen.add(job.job_id)
            out.append(job)


def same_host_link(base, href):
    url = urljoin(base, href)
    if urlparse(url).netloc != urlparse(base).netloc:
        raise ValueError("Unexpected pagination host")
    return url
