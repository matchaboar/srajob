// Helper function to evaluate XPath and return the first matching element
function getElementByXPath(xpath, parent = document) {
    let result = document.evaluate(
        xpath,
        parent,
        null,
        XPathResult.FIRST_ORDERED_NODE_TYPE,
        null
    );
    return result.singleNodeValue;
}

// 1. Find the pagination container using the baseSelector
function checkForNextPage(baseSelector, selector) {
    const paginationContainer = getElementByXPath(baseSelector);
    if (paginationContainer) {
        // 2. Within the pagination container, find the next page button using the field's selector
        const nextPageButton = getElementByXPath(selector, paginationContainer);
        if (nextPageButton) {
            // 3. If found, return true to tell scraper to stop waiting to click.
            return true;
        } else {
            console.log("Next page button not found.");
            return false;
        }
    } else {
        console.log("Pagination container not found.");
        return false;
    }
}