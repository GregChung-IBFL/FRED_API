# FRED_API Demo
This program demonstrates using the Federal Reserve Economic Data (FRED®) API.  The demo queries the API to map the data available from FRED.  The structure of the data can be represented in a tree hierarchy.

- Coded in Python, with add-on libraries [treelib](https://treelib.readthedocs.io), [PyYAML](https://pyyaml.org)
- Queries REST API of an external service 
- Implements a basic caching module to cache API requests
- Configuration and settings stored in .json and .yaml files, not in code

#### Version History
- v1: The API is queried to generate the layout of data Categories and Series.  The tree layout is saved to a text file.


## About the FRED service
FRED is a service provided by the Federal Reserve Bank of St. Louis.  See https://fred.stlouisfed.org/ for more information.

#### Structure of the Data
The economic data is represented by Series, which are organized under nested layers of Categories.  From the handful of top-level categories, you can drill down into increasingly more specific subcategories until you reach a data series.  For example:

* &lt;FRED API root&gt; (category #0)
  * Population, Employment, & Labor Markets (category #10)
    * Weekly Initial Claims (category #32240)
      * 4-Week Moving Average of Initial Claims (series IC4WSA)

Note: some data series are listed under more than one category.

#### Developer API Key
A private developer API key is required to access the FRED API.  In order to run the demo code, you would need to request your own API key, as my key is not included in this project.  Because the code will not run out-of-the-box, I have included sample output and logging files.

