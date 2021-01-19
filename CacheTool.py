
import json
import logging
from datetime import datetime, timezone, timedelta

DEFAULT_CACHE_EXPIRATION = 24           # Expiration, in hours
DEFAULT_CACHE_FILE_NAME = "cache.json"  # Imaginative, isn't it?

class Cacher :
    """My basic tool for caching data.  For this demo, it caches the API's responses in order
    to reduce the number of times I hit the server during development & debugging.
    
    Implemented as a (cache key) dictionary of (cache values) dictionaries.  The values contain
    a timestamp with the actual cached data.  The timestamp (UTC) tracks when the data was
    written to the cache.  Data older than a specied cutoff is expired and will not be used.
    
    There are a few configurable settings which are specified during initialization.  
    The cache is persisted to a JSON formatted file.  The file is loaded automatically upon
    initialization of the Cacher, and fully re-written using an explicit function call.

    Cache usage metrics are tracked by a nested CacheStats class.

    The Cacher utilizes the root logger, which must be initialized first.
    
    Exceptions raised within the Cacher are logged but are not fatal.

    This code is intentionally simple; it doesn't try to do any cleanup of old cache entries,
    enforce a cache size limit, track the most-recent access times, count the number of times
    a key is requested, etc.  None of these features are needed for this code sample, and I'm
    sure there are libs out there which do this kind of thing.
    """

    class CacheStats:
        def __init__(self):
            self.num_hits = self.num_misses = self.num_expired = self.num_invalid = 0
        def hit(self):
            self.num_hits += 1
        def miss(self):
            self.num_misses += 1
        def expired(self):
            self.num_expired += 1
        def invalid(self):
            self.num_invalid += 1

    def __init__(self, enabled, cache_file_name, cache_expiration_hours ):
        logging.debug( F'Initializing Cacher: file = "{cache_file_name}", expire in hours = {cache_expiration_hours}' )
        self.enabled = enabled
        if not enabled :
            logging.debug( "Cacher is disabled" )
        self.cache_file_name = cache_file_name
        self.cache_expiration_hours = cache_expiration_hours
        self.cache_dict = {}
        self.stats = self.CacheStats()
        self.load_cache_file()

    def get_stats(self) :
        """Returns a dictionary of the accumulates metrics from CacheStats."""
        return self.stats.__dict__.copy()


    def load_cache_file(self) :
        """Reads the JSON encoded cache file back into Cacher memory."""
        if not self.enabled :
            return

        try:
            with open( self.cache_file_name, "r" ) as file:
                self.cache_dict = json.load( file )
        except FileNotFoundError:
            logging.info( F'Cache file "{self.cache_file_name}" not found.' )
        except Exception as e:
            # Disable the cache to prevent overwriting the existing file, so we have a chance to inspect/debug the bad file.
            self.enabled = False
            logging.warning( F'Cache file "{self.cache_file_name}" failed to load.  Cache will not be used.' )
        else:
            logging.info( F'Loaded cache file "{self.cache_file_name}".' )


    def save_cache_file(self) :
        """Saved the cache to the JSON encoded file, overwriting existing file.
        All entries in the cache memory are written to the cache file.
        """
        if not self.enabled :
            return

        try:
            with open( self.cache_file_name, "w" ) as file:
                json.dump( self.cache_dict, file, indent = 4 )
        except:
            # TODO: In a real program, I would handle specific errors, e.g. permission denied.
            logging.error( F'Failed to save cache file "{self.cache_file_name}".' )
        else:
            logging.info( F'Saved cache file "{self.cache_file_name}".' )


    def read_cached_data( self, key ) :
        """Returns the cached data for the specified @key, if data is available and not expired.
        Returns None if the @key was not found, or if it was found but its data has expired.
        """
        if not self.enabled :
            return None

        # Check the cache to see if there is data for the specified key.
        cache_entry = self.cache_dict.get( key )
        if cache_entry is None :
            logging.debug( F'Cache does not contain "{key}".' )
            self.stats.miss()
            return None

        # Found an entry in the cache for this key, but have to check the expiration date.
        timestampStr = cache_entry.get( "timestamp" )
        if timestampStr :
            try:
                timestampUTC = datetime.fromisoformat( timestampStr )
                if ( datetime.now(timezone.utc) - timestampUTC) < timedelta( hours = self.cache_expiration_hours ) :
                    # The timestamp is valid, return the corresponding data.
                    logging.debug( F'Returning cache for "{key}".' )
                    self.stats.hit()
                    return cache_entry.get( "data" )
                else:
                    # Reminder: this sample code does not cleanup expired entries.
                    logging.debug( F'Cached expired for "{key}".' )
                    self.stats.expired()
                    return None
            except Exception as e:
                pass    # Fall through

        # Couldn't find the timestamp, or couldn't parse it, or something else bad happened.
        # Log it, and return nothing.
        logging.debug( F'Cache for "{key}" is missing or has an invalid timestamp.' )
        self.stats.invalid()
        return None


    def write_cached_data( self, key, data ) :
        """Writes a cache entry for @key = @data into the memory cache.
        @key is unique; writing to the same @key a second time will overwrite any existing value.
        The current timestamp, in UTC, is recorded with the cache entry.

        A cache entry is structured as such:
            {
                @key : {
                            "timestamp" : "2021-01-01T09:30:00.000000+00:00"
                            "data" : @data
                       }
            }
        """
        if not self.enabled :
            return

        # Timestamp is the current UTC time in ISO format, e.g. "2021-01-01T09:30:00.000000+00:00"
        cache_entry = { "timestamp" : datetime.now( timezone.utc ).isoformat(), 
                        "data" : data }
        self.cache_dict[key] = cache_entry

# End of class Cacher



def initialize( enabled = True, cache_file_name = DEFAULT_CACHE_FILE_NAME, expire_in_hours = DEFAULT_CACHE_EXPIRATION ) :
    """Initialize and return a new instance of a Cacher.
    The Cacher will automatically attempt to read in the existing cache file, if available.
    """
    return Cacher( enabled, cache_file_name, expire_in_hours )



if __name__ == "__main__":
    print("CacheTool is not directly runnable.")
