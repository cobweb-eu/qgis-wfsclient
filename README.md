# qgis-wfsclient

/***************************************************************************
*                                                                         *
*   This version of the WFS 2.0 plugin supports the SAML ECP login        *
*   Developed under COBWEB prokect with the following limitation          *
*   This version does not allow to select the IdP. The COBWEB IdP is      *
*   hardcoded. For login with another IdP of the COBWEB federation        *
*   the instantiation of ECPDownloader must use the other IdP's URL       *
*   Addtional info: Due to the limitations of the OpenID protocoll, it is *
*   not possible to use the GMail or Facebook IdPs with this plugin!      *
*   Todo: Implement a SAML metadata reader that parses a federation meta- *
*   data and displays the list of available IdPs (all those that support  *
*   ECP) in a pull-down menu to the user.
*                                                                         *
***************************************************************************/
