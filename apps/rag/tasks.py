from celery import shared_task

@shared_task
def process_rag_task(task_id):
    pass

"""
Vì dữ liệu RAG sẽ được xử lý bởi một microservice riêng biệt bằng FastAPI, nên task này sẽ gửi dữ liệu RAG đến microservice đó để xử lý. 
Việc xử lý này sẽ là bất đồng bộ nên chúng ta sẽ không cần nhận dữ liệu ngay lập tức từ microservice, mà sẽ nhận dữ liệu sau khi microservice xử lý xong. 
Do đó, task này sẽ chỉ gửi dữ liệu RAG đến microservice và không cần nhận dữ liệu trả về ngay lập tức.
"""