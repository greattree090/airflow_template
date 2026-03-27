"""샘플 DAG - Hello Airflow

간단한 BashOperator 예제로, Airflow가 정상 동작하는지 확인하는 용도입니다.
매일 자정(UTC)에 실행되며, 수동 트리거도 가능합니다.
"""

from datetime import datetime

from airflow.sdk import DAG, task


@task
def say_hello():
    print("Hello, Airflow!")


@task
def say_goodbye():
    print("Goodbye, Airflow!")


with DAG(
    dag_id="example_dag",
    description="동작 확인용 샘플 DAG",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["example"],
) as dag:
    say_hello() >> say_goodbye()
