"""Allow reference sections by :ref: role using its title."""

from __future__ import annotations

from types import NoneType
from typing import TYPE_CHECKING, cast
from importlib import import_module
from collections.abc import Callable

from docutils import nodes

import sphinx
from sphinx.locale import __
from sphinx.util import logging
from sphinx.util.nodes import clean_astext

if TYPE_CHECKING:
    from docutils.nodes import Node

    from sphinx.application import Sphinx
    from sphinx.util.typing import ExtensionMetadata

logger = logging.getLogger(__name__)


def get_node_depth(node: Node) -> int:
    i = 0
    cur_node = node
    while cur_node.parent != node.document:
        cur_node = cur_node.parent
        i += 1
    return i

def get_slug_func(app: Sphinx) -> Callable[[str], str]:
    """Support a custom slugging function, such as myst_parser.mdit_to_docutils.base.default_slugify."""
    slug_func = app.config.autosectionlabel_slug_func
    if slug_func is None:
        return None
    if isinstance(slug_func, str):
        try:
            module_path, function_name = slug_func.rsplit('.', 1)
            mod = import_module(module_path)
            func = getattr(mod, function_name)
        except (ImportError) as exc:
            raise TypeError(f'Failed to import slug function: {slug_func}') from exc
    if not callable(func):
        raise TypeError(f'Slug function {slug_func} is not callable')
    return func

def register_sections_as_label(app: Sphinx, document: Node) -> None:
    domain = app.env.domains.standard_domain
    slug_func = get_slug_func(app)

    for node in document.findall(nodes.section):
        if (
            app.config.autosectionlabel_maxdepth
            and get_node_depth(node) >= app.config.autosectionlabel_maxdepth
        ):
            continue
        labelid = node['ids'][0]
        docname = app.env.docname
        title = cast('nodes.title', node[0])
        ref_name = getattr(title, 'rawsource', title.astext())
        if slug_func is not None:
            ref_name = slug_func(ref_name)
        if app.config.autosectionlabel_prefix_document:
            name = nodes.fully_normalize_name(docname + ':' + ref_name)
        else:
            name = nodes.fully_normalize_name(ref_name)
        sectname = clean_astext(title)

        logger.debug(
            __('section "%s" gets labeled as "%s"'),
            ref_name,
            name,
            location=node,
            type='autosectionlabel',
            subtype=docname,
        )
        if name in domain.labels:
            logger.warning(
                __('duplicate label %s, other instance in %s'),
                name,
                app.env.doc2path(domain.labels[name][0]),
                location=node,
                type='autosectionlabel',
                subtype=docname,
            )

        domain.anonlabels[name] = docname, labelid
        domain.labels[name] = docname, labelid, sectname


def setup(app: Sphinx) -> ExtensionMetadata:
    app.add_config_value(
        'autosectionlabel_prefix_document', False, 'env', types=frozenset({bool})
    )
    app.add_config_value(
        'autosectionlabel_maxdepth', None, 'env', types=frozenset({int, NoneType})
    )
    app.add_config_value(
        'autosectionlabel_slug_func', None, 'env', types=frozenset({str, Callable})
    )
    app.connect('doctree-read', register_sections_as_label)

    return {
        'version': sphinx.__display_version__,
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
