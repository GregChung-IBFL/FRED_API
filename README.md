# FRED_API
[python]

This is a demo of browsing the data structure of Federal Reserve Economic Data (FRED®) through its REST API.  FRED provides a tree-like structure, with nested layers of categories and data series under those categories.  The API does not provide a way to search or browse the data structure; to find some series of interest, you must start with the top-level category, then drill down into narrower categories until you find the desired series.  The demo traverses this structure and outputs the data layout.


## More about the FRED service
FRED is a service provided by the Federal Reserve Bank of St. Louis.  To use the API, you must first receive a developer API key.  This key is passed in as a URL parameter in all calls to the API.  See https://fred.stlouisfed.org/ for more information about FRED as well as the developer API.
Note:  While the API does not have search or browse capabilities to find a particular series, the interactive website does provide search tools.
