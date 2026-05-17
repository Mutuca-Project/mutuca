# from datetime import datetime

# import scrapy


# class BaseCaruaruParliamentaryAllowanceSpider(scrapy.Spider):
#     def __init__(
#         self, start_date="01/01/2000", end_date=None, row_count="-1", *args, **kwargs
#     ):
#         super(BaseCaruaruParliamentaryAllowanceSpider, self).__init__(*args, **kwargs)

#         self.start_date = start_date
#         self.row_count = row_count

#         if end_date is not None:
#             try:
#                 self.end_date = datetime.strptime(end_date, "%d/%m/%Y").date()
#                 self.logger.info(f"Collecting data until {self.end_date}")
#             except ValueError:
#                 self.logger.exception(
#                     f"Unable to parse {end_date}. Use %d/%m/%Y date format."
#                 )
#                 raise
#         elif hasattr(self, "end_date"):
#             self.logger.info(f"Collecting data until {self.end_date}")
#         else:
#             self.end_date = datetime.now().strftime("%d/%m/%Y")
#             self.logger.info("Collecting all data available until now")
