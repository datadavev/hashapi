# README for hashapi/app

This is a fastapi REST API for hashstore.

Current implementation is readonly, with basic support for retrieving information about entries and the entries themselves.

The app is designed to operate with Apache as the proxy service since it leverages `mod_xsendfile` to handle access to the data files contained in hashstore.
