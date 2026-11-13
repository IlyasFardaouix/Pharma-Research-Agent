"""Assemble the agent-callable tools.

Returns two things:

* ``tools`` — LangChain ``StructuredTool`` objects, used only to advertise each
  tool's name/description/args schema to the LLM (``llm.bind_tools``). The agent
  decides which to call; nothing is hardcoded.
* ``handlers`` — name -> callable returning a rich :class:`ToolResult`, used by the
  custom tools node so we can capture structured passages/citations into state.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.tools import StructuredTool

from app.rag.index import CorpusIndex
from app.tools import glossary, search, sections
from app.tools.base import ToolResult


def _validated(schema, fn: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
    """Coerce/validate model-supplied args against the tool's pydantic schema first.

    A bad argument (wrong type, out-of-range ``k``, missing field) raises here and is
    surfaced to the agent as a tool error instead of crashing or overflowing context.
    """
    def handler(**raw) -> ToolResult:
        return fn(**schema(**raw).model_dump())
    return handler


def build_tools(
    corpus: CorpusIndex,
) -> tuple[list[StructuredTool], dict[str, Callable[..., ToolResult]]]:
    handlers: dict[str, Callable[..., ToolResult]] = {
        "search_corpus": _validated(search.SearchArgs, lambda **a: search.run(corpus, **a)),
        "get_drug_section": _validated(sections.SectionArgs, lambda **a: sections.run_section(corpus, **a)),
        "list_drugs": lambda **a: sections.run_list(corpus),
        "lookup_glossary": _validated(glossary.GlossaryArgs, lambda **a: glossary.run(corpus, **a)),
    }

    tools = [
        StructuredTool.from_function(
            name="search_corpus",
            description=search.DESCRIPTION,
            args_schema=search.SearchArgs,
            func=lambda query, k=5, drug=None: handlers["search_corpus"](
                query=query, k=k, drug=drug
            ).content,
        ),
        StructuredTool.from_function(
            name="get_drug_section",
            description=sections.SECTION_DESCRIPTION,
            args_schema=sections.SectionArgs,
            func=lambda drug, section, source="dailymed", product_id=None, allow_fallback=False: handlers["get_drug_section"](
                drug=drug, section=section, source=source, product_id=product_id, allow_fallback=allow_fallback
            ).content,
        ),
        StructuredTool.from_function(
            name="list_drugs",
            description=sections.LIST_DESCRIPTION,
            args_schema=sections.ListDrugsArgs,
            func=lambda: handlers["list_drugs"]().content,
        ),
        StructuredTool.from_function(
            name="lookup_glossary",
            description=glossary.DESCRIPTION,
            args_schema=glossary.GlossaryArgs,
            func=lambda term: handlers["lookup_glossary"](term=term).content,
        ),
    ]
    return tools, handlers
