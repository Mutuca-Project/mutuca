# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface

from pathlib import PurePosixPath
from urllib.parse import urlparse

# from itemadapter import ItemAdapter
from scrapy.pipelines.files import FilesPipeline


class ParliamentaryAllowancePipeline(FilesPipeline):
    def file_path(self, request, response=None, info=None, *, item=None):
        return "pdf/" + PurePosixPath(urlparse(request.url).path).name
