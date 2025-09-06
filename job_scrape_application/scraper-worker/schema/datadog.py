schema = {
    "name": "Job Listings",
    "baseSelector": "//li[contains(@class, 'ais-Hits-item')]",
    "fields": [
        {
            "name": "job_title",
            "selector": ".//h3[contains(@class, 'job-title')]",
            "type": "text",
        },
        {
            "name": "department",
            "selector": ".//div[contains(@class, 'job-card-department')]/p",
            "type": "text",
        },
        {
            "name": "location",
            "selector": ".//div[contains(@class, 'job-card-location')]/p",
            "type": "text",
        },
        {"name": "job_url", "selector": ".//a", "type": "attribute", "attribute": "href"},
    ],
}
