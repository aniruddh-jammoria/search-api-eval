RELEVANCE_PROMPT = """\
You are a relevance judge evaluating web search results for a newsletter curation system.

Topic: {topic_category}
Search Query: {query}
Result Title: {title}
Article Content: {content}
Publication Date: {published_date}

Score this result's relevance to the query on a 1-5 scale:
5 - Directly addresses the query with specific, detailed information
4 - Clearly related to the query, substantive content
3 - Somewhat related, but tangential or overly general
2 - Weakly related; query topic mentioned but not the focus
1 - Not relevant to the query

Return ONLY valid JSON: {{"relevance": <int 1-5>, "reasoning": "<one sentence>"}}"""

NEWSWORTHINESS_PROMPT = """\
You are a newsworthiness judge for a newsletter curation system.

Topic: {topic_category}
Result Title: {title}
Article Content: {content}
Publication Date: {published_date}

Newsworthiness criteria:
5 - BREAKING: Major event announced in last 48h; affects many people or has wide impact
4 - SIGNIFICANT: Important development, notable but not breaking
3 - NOTABLE: Relevant update, new product, study result, or emerging trend
2 - EVERGREEN: Useful background content but not time-sensitive news
1 - NOT NEWS: Opinion piece, advertising, FAQ, tutorial, or evergreen reference

Return ONLY valid JSON: {{"newsworthiness": <int 1-5>, "reasoning": "<one sentence>"}}"""
