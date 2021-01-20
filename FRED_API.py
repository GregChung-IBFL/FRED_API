"""
Greg Chung

Sample program to demonstrate getting data from the Federal Reserve Economic 
Data (FRED®) API.  The application downloads the available "Category" and 
data "Series" information using the REST API, and presents a hierarchical
representation of the data, e.g.:
    <root>
        <category1>
        <category2>
            <series2.1>
            <series2.2>
        <category3>
            <series3.1>
    etc.

Interesting features:
    * treelib package is used to represent the data layout and to generate the output
    * Uses YAML (PyYAML) and JSON for config and cache files
    * I use my own demo caching module, CacheTool.py

    v1: Downloads the API data layout and generates the tree file using treelib

"""
import json
import os
import re       # standard library for reg ex
import urllib.request
from time import sleep
from datetime import datetime
import logging
import logging.config

import CacheTool    # My little caching tool for calls to the server, (key) URL -> (value) responses

# Additional installed libraries:
import yaml
from treelib import Node, Tree


# Useful "constants":
CONFIG_FILE_LOGGING = "logging_config.yaml"     # Config for the logging libary
CONFIG_FILE_APP = "config.yaml"                 # Config for the application
API_KEY_FILE_NAME = "api_key.json"              # Contains the private API key (do not add to source control!)
API_KEY_PARAM_NAME = "api_key"                  # The name of the API key parameter in the URL


class Application :
    class AppStats :
        def __init__(self) :
            self.total_categories = self.total_series = self.total_server_calls = 0
        def inc_categories(self, num = 1) :
            self.total_categories += num
        def inc_series(self, num = 1) :
            self.total_series += num
        def inc_server_calls(self) :
            self.total_server_calls += 1

    def get_stats(self) :
        return self.stats.__dict__.copy()

    def __init__(self) :
        self.stats = self.AppStats()
        self.API_KEY_PARAMETER = None

    def initialize(self) :
        """Initialize the application.

        Includes the initialization of data objects, logging library, and the data caching tool.

        Reads the configuration and API key files.
        The configuration file is loaded into the CONFIG dictionary.  All program settings
        should be specified in the config file, rather than hard-coded here.  The JSON
        config file is easy to understand and edit by hand.  The following values should
        be specified:

            CONFIG["FRED_API"]["BASE_URL"]      # URL of the FRED API
            CONFIG["FRED_API"]["ROOT_CATEGORY"] # Which category to start from, 0 is the topmost category published by FRED
            CONFIG["FRED_API"]["LIMIT_DEPTH"]   # How many levels down below the root do we want to expand?
            CONFIG["FRED_API"]["LIMIT_SERIES"]  # Maximum number of series under each category to request/cache/display
            CONFIG["FRED_API"]["THROTTLE"]      # Seconds to pause between API calls, to avoid running afoul of terms of use by spamming it with requests

            CONFIG["API_CACHE"]["FILE"]         # Name of the file which caches the API requests via CacheTool
            CONFIG["API_CACHE"]["EXPIRE"]       # Number of hours after which cached API requests expire (are stale)

            CONFIG["OUTPUT_FILE_TEXT"]          # Name of the file to write the API data layout (ASCII format)

        The JSON file designated to store the secret API key used for all FRED API calls is
        parsed, and the value populated into URL-parameterized string, API_KEY_PARAMETER.
        The (private) key is stored in its own file to reduce the chance that my key is 
        accidentally published, i.e. definitely it is not hard-coded into this module,
        and the key file must not be added to source control.  If missing or broken, the
        file can be easily recreated:

            api_key.json:
            {
                "api_key" : "abcdefghijklmnopqrstuvwxyz123456"
            }
        """

        # 1. Initialize the logging package:
        try:
            with open( CONFIG_FILE_LOGGING, "r") as file:
                configDict = yaml.safe_load( file )
                logging.config.dictConfig( configDict )
        except:
            print( F'Failed to configure logging from "{CONFIG_FILE_LOGGING}", aborting!' )
            exit( -985 )
        else:
            logging.debug("Logging initialized.")

        # 2. Load the application's configuration:
        try:
            with open( CONFIG_FILE_APP, "r") as file:
                self.CONFIG = yaml.safe_load( file )
        except:
            logging.critical( F'Failed to read application configuration from "{CONFIG_FILE_APP}", aborting!' )
            exit( -990 )
        else:
            logging.info("Application configuration loaded.")
            logging.debug( self.CONFIG )

        # 3. Load the secret API key used:
        try:
            with open( API_KEY_FILE_NAME, "r") as file:
                api_key_dict = json.load( file )
                api_key = api_key_dict.get( "api_key" )
                # As per https://fred.stlouisfed.org/docs/api/api_key.html the API key 
                # is a 32 character lower-cased alpha-numeric string.
                # TODO: Validate the key only contains valid characters, etc.
                if not api_key or len(api_key) != 32 :
                    raise Exception( '"api_key" value missing or improperly formatted' )
                self.API_KEY_PARAMETER = API_KEY_PARAM_NAME + "=" + api_key
        except Exception as e:
            logging.critical( F'Failed to load API key from "{API_KEY_FILE_NAME}", aborting!\n{str(e)}' )
            exit( -995 )
        else:
            logging.info("FRED API key loaded.")

        # 4. Initialize the caching tool to cache API requests & responses:
        self.APICacher = CacheTool.initialize(  enabled = self.CONFIG["API_CACHE"]["ENABLED"],
                                                cache_file_name = self.CONFIG["API_CACHE"]["FILE"], 
                                                expire_in_hours = self.CONFIG["API_CACHE"]["EXPIRE"] )

        # 5. Initialize a treelib tree to represent the data layout:
        self.fred_data_tree = self.initialize_tree()


    def make_api_request( self, requestURL ) :
        """Makes a GET request to the API at @requestURL.

        Simplistic throttling in the form of a sleep() is done here to prevent rapid spamming
        the API.  I expect that if there is one URL which wasn't read from the cache, then none
        the URLs will be read from the cache.  
        """
        self.stats.inc_server_calls()
        sleep( self.CONFIG["FRED_API"]["THROTTLE"] )

        # API key was omitted from the URL to avoid the cache storing the API key value.
        urlWithKey = requestURL + "&" + self.API_KEY_PARAMETER
        req = urllib.request.Request( urlWithKey )

        # Read back the results, decoding the bytes to text.
        try:
            with urllib.request.urlopen(req) as response :
                return response.read().decode("utf-8")
        except Exception as e:
            logging.error( F'Exception occurred in API call to "{requestURL}":\n{str(e)}' )

        return None

    def make_caching_request( self, requestURL ) :
        """Gets the response for the @requestURL, from the cache if avaiable, else
        from the API host.

        The response for @requestURL may be returned from the cache, if found and not 
        expired.  Upon a cache miss, the request is made to the API host, and its
        response is saved back to the cache.

        The return value is the simply the response decoded to a UTF-8 string (JSON).
        """
        # If available, use what's in the cache.
        data = self.APICacher.read_cached_data( requestURL )
        if not data :
            # If this URL wasn't available from the cache, or it was too old,
            # execute the actual API call, and save the response to the cache.
            data = self.make_api_request( requestURL )
            self.APICacher.write_cached_data( requestURL, data )

        return data


    def get_rest_data( self, rest_path ) :
        """Returns the data from the @rest_path, decoded into a dictionary.
        @rest_path is the REST path and associated parameters for the data only.
        
        The private api_key to access FRED must not be specified in @rest_path,
        as doing so would cause it to be saved to the cache file.  Thus, I
        specifically test for its presence and abort if I find it.
        """
        # Assemble the full URL from the URL root plus the specified rest_path.  Does not include the api_key!
        fullURL = "{base_url}/{rest_path}&file_type=json".format( base_url = self.CONFIG["FRED_API"]["BASE_URL"], rest_path = rest_path )

        # Sanity check: look for the api_key and abort if found in the URL.
        if API_KEY_PARAM_NAME in rest_path.lower() :
            logging.critical( F'Requested URL "{fullURL}" contains the "{API_KEY_PARAM_NAME}" parameter.  THIS IS A CODING BUG!  Aborting!' )
            exit( -999 )

        # Get the data for the URL, then decode it.
        try:
            data = self.make_caching_request( fullURL )
            return json.loads(data)  
        except:
            logging.error( F'Failed to get or decode response for "{fullURL}"!' )
        
        # Return an empty dict
        return {}


    def get_child_categories( self, parentCategoryID ) :
        """Gets a list of child categories under the specified @parentCategoryID.

        Returns the categories directly under the @parentCategoryID, as a dictionary
        containing summary info and a list of dictionaries representing the child categories.
        """
        url = F'category/children?category_id={parentCategoryID}'
        return self.get_rest_data( url )

    def get_children_series( self, parentCategoryID ) :
        """Gets a list of child series under the specified @parentCategoryID.

        The number of series requested is limited via the application configuration,
        as a category can contain 1000s of series, and I only want to show a small sample.

        Returns the series directly under the @parentCategoryID, as a dictionary.
        containing summary info and a list of dictionaries representing the child series.
        """
        url = "category/series?category_id={category_id}&limit={limit}".format( category_id = parentCategoryID, limit = self.CONFIG["FRED_API"]["LIMIT_SERIES"] )
        return self.get_rest_data( url )


    def process_series( self, series: dict, categoryID: str, tree ) :
        """Process a data series by appending the @series info into the @tree 
        as a child of the tree node identified with @categoryID.

        The series is represented in the tree with a header node listing its ID and title.
        Child nodes of the header include a brief excerpt of the series' notes text, and 
        a list of key attributes of the series, such as the data update frequency.
        """
        def reformat_date_string( api_datetime: str ) -> str:
            """Returns the @api_datetime string translated into a different display format.

            Used for reformatting last updated and observation range dates.  I parse the
            @api_datetime string (see below for expected input formats) into a datetime,
            then output a new string under my preferred format.
            There appear to be two date formats returned by the API:
                1. Date & time, including UTC offset.  Parsing these requires a data fudge because
                   the UTC offset contains only two digits (the hours) while the strptime() expects
                   four digits (hours and minutes).  I pad the input string with "00" to allow the
                   parser to work.
                2. Date-only in the form of YYYY-MM-DD.
            I use a list of reformatting rules for the above, which are applied in order.  If
            another format is found later, it can be handled by adding it to data_formats[] below.
            """
            date_formats = [ ("%Y-%m-%d %H:%M:%S%z", "%b %d, %Y %r", "00"), # 2021-01-17 17:43:24-05 --> Jan 17, 2021 05:43:24 PM (local time)
                             ("%Y-%m-%d", "%b %d, %Y", "") ]                # 1995-07-01 --> Jul 01, 1995

            for inputFormat, outputFormat, inputTZFudge in date_formats :
                try:
                    test = api_datetime + inputTZFudge
                    date = datetime.strptime( test, inputFormat )
                    return datetime.strftime( date, outputFormat )
                except:
                    pass # Eat the exception and try the next format

            # If unable to reformat the input, log a warning and just return the original.
            logging.warning( F'Unable to parse datetime "{api_datetime}", check parsing format' )
            return api_datetime

        # Series header node contains the ID and Title.  The node identifier is a combination of
        # the category ID & series ID.  Series ID alone is inadequate because the same series can
        # appear under multiple categories, but tree nodes must have unique identifiers.
        text = "[{id}] {title}".format( title = series["title"], id = series["id"] )
        nodeIdentifier = "{categoryID}/{seriesID}".format( categoryID = str(categoryID), seriesID = str(series["id"]) )
        tree.create_node( text, nodeIdentifier, parent = str(categoryID) )

        # The notes can be quite long and can contain newlines encoded as \n and also \r\n.  For a
        # cleaner display, I replace any/all consecutive newlines with a single space, using regex
        # string replacement.  The output is truncated, and the excess length is reported.
        notes = series.get("notes")
        if notes :
            text = re.sub( "[\r\n]+", " ", notes[:9999] )   # Sanity check max notes length
            max_display_len = 100
            text_len = len(text)
            if text_len >= max_display_len :
                # Typical long notes can go into 1000s of chars.  Long notes are truncated then
                # and displayed as '"<truncated long text>..." [+1234]'.
                text = '"' + text[:max_display_len] + '..." [+{num_truncated}]'.format( num_truncated = text_len-max_display_len )
            else :
                text = '"' + text + '"'
            tree.create_node( text, parent = nodeIdentifier )

        # The attributes text includes any of the following, if they are defined on the series:
        #     <update frequency> -- e.g. "Annual", "Monthly", "Daily", etc.
        #     "Seasonally Adjusted" -- only if applicable
        #     "Updated" -- (reformatted) date & time of the last series update
        #     "Observations" -- range of (reformatted) start and end dates
        attributes = []

        frequency = series.get("frequency")
        if frequency :
            attributes.append( frequency )

        # Include "Seasonally Adjusted" if set, ignore "Not Seasonally Adjusted"
        seasonal = series.get("seasonal_adjustment")
        if seasonal and series.get("seasonal_adjustment_short") == "SA" :
            attributes.append( seasonal )

        last_updated = series.get("last_updated")
        if last_updated :
            attributes.append( "Updated {updated}".format(updated = reformat_date_string(last_updated)) )

        observation_start = series.get("observation_start")
        observation_end = series.get("observation_end")
        if observation_start and observation_end :
            attributes.append( "Observations {datefrom} to {dateto}".format(datefrom = reformat_date_string(observation_start), dateto = reformat_date_string(observation_end)) )

        if attributes :
            tree.create_node( "; ".join(attributes), parent = nodeIdentifier )

        # TODO:  Many series contain copyright data requiring approval to use.  To determine this,
        # I would need to call the API "series/tags" on individual series.  If building a tool to
        # access specific series, the various "copyrighted_*" tags must be checked.


    def process_category( self, depth, categoryDict, tree ) :
        """Process an API category, by building summaries of its first N data series
        children, then recursively processing all child subcategories.
        @categoryDict must contain values for id and name.  Other values are not used.

        Returns a tuple containing the total number of descendent categories, and the total number
        of descendent series; includes immediate children, plus all grandchildren, etc.

        Recursion stops at the maximum traversal depth (application configuration).
        Data below this depth limit is not visited, thus any categories and series
        they might contain are not included in the counts.

        Side Note: the plural of "series" is "series" which is awkward.
        """
        def process_children_series( self, children_series, categoryID, tree ) :
            num_series = children_series.get("count")   # The total number of series which exist, NOT the number of series fetched!
            seriess = children_series.get("seriess")    # "seriess" is not a typo; contains a list of the children.

            if num_series and seriess :
                self.stats.inc_series( num_series )
                num_descendent_series = num_series

                # Cap the number of series displayed, because some categories have thousands.  The code
                # requests a limited number of series from the API, but enforce the cap here as well.
                num_remaining = num_series
                for series in seriess[ : self.CONFIG["FRED_API"]["LIMIT_SERIES"]] :
                    self.process_series( series, categoryID, tree )
                    num_remaining -= 1

                if num_remaining > 0 :
                    text = F"plus {num_remaining} additional series..."
                    tree.create_node( text, parent = str(categoryID) )
            else :
                num_series = 0
                num_descendent_series = 0

            return ( num_series, num_descendent_series )


        if depth > self.CONFIG["FRED_API"]["LIMIT_DEPTH"] :
            return (0, 0)   # number of descendent Categories, Series

        categoryID = categoryDict["id"]
        categoryName = categoryDict["name"]

        # To show progress, especially when making API calls, display the category.
        text = "{indent}[#{category}] {name}".format(indent = " " * (4 * depth), name = categoryName, category = categoryID) 
        logging.info( text )

        # On errors, this can return an empty dict, so be prepared to handle it.
        children_series = self.get_children_series( categoryID )
        (num_series, num_descendent_series) = process_children_series( self, children_series, categoryID, tree )

        # On errors, this can return an empty dict, so be prepared to handle it.
        children_categories = self.get_child_categories( categoryID )
        categories = children_categories.get("categories")
        if categories :
            num_categories = len(categories)
            num_descendent_categories = num_categories
            self.stats.inc_categories( num_categories )

            for subdict in categories :
                text = "[#{id}] {name}".format( name = subdict["name"], id = subdict["id"])
                tree.create_node( text, str(subdict["id"]), parent = str(categoryID) )

                num_descendents = self.process_category( depth = depth+1, categoryDict = subdict, tree = tree )
                num_descendent_categories += num_descendents[0]
                num_descendent_series += num_descendents[1]
        else :
            num_categories = num_descendent_categories = 0


        # If the category has any descendent categories and/or series, update the category node
        # with the counts.  Get the existing node in the tree, then modify it to append new text.
        cat_node = tree.get_node( str(categoryID) )
        if num_categories > 0 or num_descendent_categories > 0 :
            cat_node.tag += ", contains {direct}/{descendent} categories".format(direct = num_categories, descendent = num_descendent_categories)
        if num_series > 0 or num_descendent_series > 0 :
            cat_node.tag += ", contains {direct}/{descendent} series".format(direct = num_series, descendent =  num_descendent_series)

        # Return the counts of the descendent categories and series
        return (num_descendent_categories, num_descendent_series)


    def initialize_tree( self ) :
        """Initializes and returns a treelib tree to represent the FRED API data layout."""
        newTree = Tree()
        newTree.create_node( "FRED® Services API at " + self.CONFIG["FRED_API"]["BASE_URL"], identifier = str(self.CONFIG["FRED_API"]["ROOT_CATEGORY"]) )
        return newTree

    def write_tree_file( self, tree ) :
        """Writes to file a text representation of the data layout tree."""
        filename = self.CONFIG["OUTPUT_FILE_TEXT"]

        try:
            os.remove( filename )
        except Exception as e:
            # Keep going despite any exceptions on the deletion, which are likely FileNotFoundError.
            logging.debug( F'Exception deleting API tree file "{filename}":\n{str(e)}' )

        try:
            tree.save2file( filename )
        except Exception as e:
            logging.error( F'Exception writing API tree file "{filename}":\n{str(e)}' )
        else:
            logging.info( F'Wrote the data tree as "{filename}".' )


    @staticmethod
    def main() :
        print("")
        print("Federal Reserve Economic Data (FRED®) API data layout walking demo.")
        print("FRED API developer information is available at https://fred.stlouisfed.org/docs/api/fred/")
        print("")
        app = Application()
        app.initialize()
        print("")

        rootCategory = app.CONFIG["FRED_API"]["ROOT_CATEGORY"] 
        rootCategoryDict = { "name" : "<root>", "id" : rootCategory }

        logging.info( F"Beginning DFS traversal of API data layout from root category #{rootCategory}:" )
        app.process_category( depth = 0, categoryDict = rootCategoryDict, tree = app.fred_data_tree )

        app.write_tree_file( app.fred_data_tree )

        app.APICacher.save_cache_file()

        appStats = app.get_stats()
        cacheStats = app.APICacher.get_stats()
        logging.debug( F"API Stats: {str(appStats)}" )
        logging.debug( F"Cacher Stats: {str(cacheStats)}" )

        print("\nDone!")
        exit(0)



if __name__ == "__main__":
    Application.main()
