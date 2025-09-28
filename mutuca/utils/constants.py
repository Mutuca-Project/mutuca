PUBLIC_WORK_DEFAULT_SELECTORS = {
    "general_info": {
        "categories": '//div[@class="row-details introducao"]//div[@class="group-title"]/text()',
        "values": '//div[@class="row-details introducao"]//div[@class="card-info"]',
    },
    "contract": {
        "categories": '//div[@class="row-group bigCard contrato"]//div[@class="row-cards"]//div[@class="row-card"]/div[@class="card-title"]/text()',
        "values": '//div[@class="row-group bigCard contrato"]//div[@class="row-cards"]//div[@class="row-card"]/div[@class="card-info"]/text()',
    },
    "contracted": {
        "categories": '//div[@class="row-group bigCard contrato"]//div[@class="row-cards"]//div[@class="row-card"]/div[@class="card-info"]/text()',
        "values": '//div[@class="row-group bigCard contratado"]//div[@class="row-cards"]//div[@class="row-card"]/div[@class="card-info"]/text()',
    },
    "fiscal_year_expenditures": {
        "categories": '//div[@class="row-group bigCard despesasExerc"]//div[@class="row-cards"]//div[@class="row-card"]/div[@class="card-title"]/text()',
        "values": '//div[@class="row-group bigCard despesasExerc"]//div[@class="row-cards"]//div[@class="row-card"]/div[@class="card-info"]/text()',
    },
    "contract_amendment": {
        "categories": '//div[@class="row-group bigCard aditivo"]//div[@class="row-cards"]//div[@class="row-card"]/div[@class="card-title"]/text()',
        "values": '//div[@class="row-group bigCard aditivo"]//div[@class="row-cards"]//div[@class="row-card"]/div[@class="card-info"]/text()',
    },
    "cumulative_amount_paid": {
        "categories": '//div[@class="row-group bigCard valorPagoAcum"]/div[@class="group-title"]/text()',
        "values": '//div[@class="row-group bigCard valorPagoAcum"]/div[@class="card-info"]/text()',
    },
    "all_documents": {
        "categories": '//section[@class="description-obra allDocuments"]//div[@class="attachment"]//p[@class="cardTitle"]/text()',
        "values": '//section[@class="description-obra allDocuments"]//div[@class="attachment"]//div[@class="button"]//a/@href',
    },
    "work_location": '//section[@class="description-obra allDocuments"]//div[@class="attachment"]//div[@class="button"]//a/@href',
}
