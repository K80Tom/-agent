"""阿里云文档智能解析器。

负责调用阿里云文档解析（大模型版），并把返回结果转换成项目统一的 ParsedDocument。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=True)

import time
from alibabacloud_credentials.client import Client as CredClient
from alibabacloud_docmind_api20220711.client import Client as DocMindClient
from alibabacloud_docmind_api20220711 import models as docmind_models
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from app.domain.interfaces.document_parser import BaseDocumentParser
from app.domain.models.parsed_document import ParsedBlock, ParsedDocument


class AliyunDocMindParser(BaseDocumentParser):
    """阿里云文档解析大模型版解析器。"""

    parser_name = "aliyun_docmind"

    def __init__(self, *, endpoint: str = "docmind-api.cn-hangzhou.aliyuncs.com") -> None:
        self.client = self._create_client(endpoint=endpoint)

    # 主要调用链路
    def parse(self, *, file_name: str, content: bytes) -> ParsedDocument:
        """把文件内容解析成统一的 ParsedDocument。"""
        task_id = self._submit_job(file_name=file_name,content=content)
        print("阿里云解析任务已提交:", task_id)
        self._wait_until_success(task_id=task_id)
        print("阿里云解析任务已完成:", task_id)

        raw_result = self._get_result(task_id=task_id)

        parsed_document = self._to_parsed_document(
        file_name=file_name,
        task_id=task_id,
        raw_result=raw_result,
        )
        print("ParsedDocument blocks:", len(parsed_document.blocks))
        return parsed_document


        # print("结果类型:", type(raw_result).__name__)
        # raw_map = raw_result
        # print("结果字段:", raw_map.keys())

        # layouts = raw_map.get("Layouts") or raw_map.get("layouts") or []
        # print("layout 数量:", len(layouts))
        # if layouts:
        #     print("第一个 layout:", layouts[0])
        
        # raise NotImplementedError("下一步再转换成 ParsedDocument")



    
    
    def _create_client(self,*,endpoint:str)-> DocMindClient:
        """创建阿里云 DocMind 客户端。"""
        cred_client = CredClient()
        credential = cred_client.get_credential()

        config = open_api_models.Config(
            access_key_id=credential.get_access_key_id(),
            access_key_secret=credential.get_access_key_secret(),
        )
        config.endpoint = endpoint

        return DocMindClient(config)
    
    
    def _submit_job(self,*,file_name:str,content:bytes) -> str:
         """提交阿里云文档解析任务，返回 task_id。"""
         file_extension = file_name.rsplit(".",1)[-1] if "." in file_name else ""

         request = docmind_models.SubmitDocParserJobAdvanceRequest(
            file_url_object=BytesIO(content),
            file_name=file_name,
            file_name_extension=file_extension,
            output_format=["markdown"],
            llm_enhancement=False,
        )

         response = self.client.submit_doc_parser_job_advance(
             request,
             util_models.RuntimeOptions(),
         )
         return response.body.data.id
    
    
    def _wait_until_success(self, *, task_id: str, interval_seconds: int = 5) -> None:
        """轮询阿里云解析任务状态，直到成功或失败。"""
        while True:
            request = docmind_models.QueryDocParserStatusRequest(id=task_id)
            response = self.client.query_doc_parser_status(request)

            status = str(response.body.data.status).lower()
            print("当前解析状态:", status)

            if status == "success":
                return

            if status in {"fail", "failed"}:
                raise RuntimeError(f"阿里云文档解析失败，task_id={task_id}")

            time.sleep(interval_seconds)
    

    def _get_result(self, *, task_id: str):
        """获取阿里云文档解析结果。"""

        request = docmind_models.GetDocParserResultRequest(
            id=task_id,
            layout_step_size=3000,
            layout_num=0,
        )

        response = self.client.get_doc_parser_result(request)
        return response.body.data
    
    def _to_parsed_document(
        self,
        *,
        file_name: str,
        task_id: str,
        raw_result: dict,
    ) -> ParsedDocument:
        """把阿里云解析结果转换成项目统一的 ParsedDocument。"""

        layouts = raw_result.get("layouts", [])
        layouts = sorted(layouts, key=lambda item: item.get("index", 0))

        blocks: list[ParsedBlock] = []

        for layout in layouts:
            content = layout.get("markdownContent") or layout.get("text") or ""
            if not content.strip():
                continue

            blocks.append(
                ParsedBlock(
                    content=content.strip(),
                    page_num=layout.get("pageNum"),
                    block_index=layout.get("index"),
                    content_type=layout.get("type"),
                    metadata={
                        "sub_type": layout.get("subType"),
                        "unique_id": layout.get("uniqueId"),
                        "level": layout.get("level"),
                    },
                )
            )
        return ParsedDocument(
                file_name=file_name,
                parser_name=self.parser_name,
                blocks=blocks,
                metadata={
                    "parser": self.parser_name,
                    "task_id": task_id,
                    "source_file": file_name,
                    "layout_count": len(layouts),
                },
            )



    









    



        
            

    