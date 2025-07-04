from datetime import timedelta
from restack_ai.workflow import workflow, import_functions, log

with import_functions():
    from src.functions.rss.pull import rss_pull
    from src.functions.crawl.website import crawl_website, CrawlInput
    from src.functions.helper.split_text import split_text, SplitTextInput
    from src.functions.llm.chat import llm_chat, FunctionInputParams
    from src.functions.rss.schema import RssInput

from pydantic import BaseModel

class RssWorkflowInput(BaseModel):
    url: str
    count: int

@workflow.defn()
class RssWorkflow:
    @workflow.run
    async def run(self, input: RssWorkflowInput):

        url = input.url
        count = input.count
        rss_results = await workflow.step(
            function=rss_pull,
            function_input=RssInput(url=url, count=count),
            start_to_close_timeout=timedelta(seconds=10))
        urls = [item['link'] for item in rss_results if 'link' in item]
        titles = [item['title'] for item in rss_results if 'title' in item]


        crawled_contents = []
        for url in urls:
            log.info("rss_result", extra={"url": url})
            if url:
                try:
                    content = await workflow.step(
                        function=crawl_website,
                        function_input=CrawlInput(url),
                        start_to_close_timeout=timedelta(seconds=30))
                    split_content = await workflow.step(
                        function=split_text,
                        function_input=SplitTextInput(text=f"{titles[urls.index(url)]}\n\n{content}"),
                        start_to_close_timeout=timedelta(seconds=30))
                    crawled_contents.append(split_content)
                except Exception as e:
                    log.error(f"Failed to crawl {url}: {str(e)}")
                    continue
        summaries = []
        for split_content in crawled_contents:
            for content in split_content:
                user_prompt = f"Provide a translation of the news article. Translate the following content to English: {content}"
                translation = await workflow.step(
                    function=llm_chat,
                    function_input=FunctionInputParams(user_prompt=user_prompt),
                    task_queue="llm_chat",
                    start_to_close_timeout=timedelta(seconds=120))

                user_prompt = f"Provide a summary of the news found on rss feed. Summarize the following content: {translation} in maxium 1 sentence with no more than 20 words"
                summary = await workflow.step(
                    function=llm_chat,
                    function_input=FunctionInputParams(user_prompt=user_prompt),
                    task_queue="llm_chat",start_to_close_timeout=timedelta(seconds=120))
                summaries.append(summary)

        user_prompt = f"Make a daily digest of all the news and tell me what is the most important news. Here are the summaries of the articles: {summaries}."

        return await workflow.step(
            function=llm_chat, 
            funcion_input=FunctionInputParams(user_prompt=user_prompt),
            task_queue="llm_chat",
            start_to_close_timeout=timedelta(seconds=120)
        )