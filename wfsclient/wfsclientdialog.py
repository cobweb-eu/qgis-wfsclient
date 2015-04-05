"""
/***************************************************************************
 WfsClientDialog
                                 A QGIS plugin
 WFS 2.0 Client
                             -------------------
        begin                : 2012-05-17
        copyright            : (C) 2012 by Juergen Weichand
        email                : juergen@weichand.de
        website              : http://www.weichand.de
 ***************************************************************************/

/***************************************************************************
WfsClientDialog With SAML ECP Support (Alpha)
A QGIS plugin
WFS 2.0 Client
-------------------
begin                : 2015-04-05
copyright            : (C) 2015 by Secure Dimensions GmbH
email                : am@secure-dimensions.de
website              : http://www.secure-dimensions.de
***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 
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

"""

from PyQt4 import QtCore, QtGui, QtXml, QtXmlPatterns
from PyQt4.QtNetwork import QHttp, QNetworkAccessManager, QNetworkRequest, QNetworkCookieJar
from PyQt4.QtCore import QUrl, QFile, QIODevice, QVariant, Qt
from PyQt4.QtGui import QProgressDialog, QLineEdit, QDialogButtonBox, QVBoxLayout, QDialog
from PyQt4.QtXml import QDomDocument, QDomNode
from ui_wfsclient import Ui_WfsClient
from qgis.core import *
from xml.etree import ElementTree
from xml.etree.ElementTree import ParseError
from osgeo import gdal
import urllib
import urllib2 
import string
import random
import tempfile
import os
import os.path
import re
import epsglib
import wfs20lib
from metadataclientdialog import MetadataClientDialog

import io, httplib, cookielib, Cookie, base64
from OpenSSL import SSL
from StringIO import StringIO

plugin_path = os.path.abspath(os.path.dirname(__file__))

class WfsClientDialog(QtGui.QDialog):

    def __init__(self, parent):
        QtGui.QDialog.__init__(self)
        # Set up the user interface from Designer.
        self.parent = parent
        self.ui = Ui_WfsClient()
        self.ui.setupUi(self)

        self.settings = QtCore.QSettings()

        self.ui.frmExtent.show()
        self.ui.frmParameter.hide()
        self.ui.progressBar.setVisible(False)
        self.ui.cmdListStoredQueries.setVisible(False)

        # Load default onlineresource
        self.ui.txtUrl.setText(self.get_url())

        self.ui.txtUsername.setVisible(False)
        self.ui.txtPassword.setVisible(False)
        self.ui.lblUsername.setVisible(False)
        self.ui.lblPassword.setVisible(False)

        self.parameter_lineedits = []
        self.parameter_labels = []

        self.init_variables()

        self.onlineresource = ""
        self.vendorparameters = ""

        self.ui.lblMessage.setText("SRS is set to EPSG: {0}".format(str(self.parent.iface.mapCanvas().mapRenderer().destinationCrs().postgisSrid())))
        self.ui.txtSrs.setText("urn:ogc:def:crs:EPSG::{0}".format(str(self.parent.iface.mapCanvas().mapRenderer().destinationCrs().postgisSrid())))

        QtCore.QObject.connect(self.ui.cmdGetCapabilities, QtCore.SIGNAL("clicked()"), self.getCapabilities)
        QtCore.QObject.connect(self.ui.cmdListStoredQueries, QtCore.SIGNAL("clicked()"), self.listStoredQueries)
        QtCore.QObject.connect(self.ui.cmdGetFeature, QtCore.SIGNAL("clicked()"), self.getFeature)
        QtCore.QObject.connect(self.ui.cmdMetadata, QtCore.SIGNAL("clicked()"), self.show_metadata)
        QtCore.QObject.connect(self.ui.cmdExtent, QtCore.SIGNAL("clicked()"), self.show_extent)
        QtCore.QObject.connect(self.ui.chkExtent, QtCore.SIGNAL("clicked()"), self.update_extent_frame)
        QtCore.QObject.connect(self.ui.chkAuthentication, QtCore.SIGNAL("clicked()"), self.update_authentication)
        QtCore.QObject.connect(self.ui.chkECP, QtCore.SIGNAL("clicked()"), self.update_authentication)
        QtCore.QObject.connect(self.ui.cmbFeatureType, QtCore.SIGNAL("currentIndexChanged(int)"), self.update_ui)
        QtCore.QObject.connect(self.ui.txtUrl, QtCore.SIGNAL("textChanged(QString)"), self.check_url)
        self.check_url(self.ui.txtUrl.text().strip())

    def init_variables(self):
        self.columnid = 0
        self.bbox = ""
        self.querytype = ""
        self.featuretypes = {}
        self.storedqueries = {}

    # Process GetCapabilities-Request
    def getCapabilities(self):
        self.init_variables()
        self.ui.cmdGetFeature.setEnabled(False);
        self.ui.cmbFeatureType.clear()
        self.ui.frmExtent.show()
        self.ui.frmParameter.hide()
        self.ui.chkExtent.setChecked(False)
        self.ui.txtExtentWest.setText("")
        self.ui.txtExtentEast.setText("")
        self.ui.txtExtentNorth.setText("")
        self.ui.txtExtentSouth.setText("")
        self.ui.cmdMetadata.setVisible(True)
        self.ui.cmdExtent.setVisible(True)
        self.ui.lblCount.setVisible(True)
        self.ui.txtCount.setText("1000")
        self.ui.txtCount.setVisible(True)
        self.ui.lblSrs.setVisible(True)
        self.ui.txtSrs.setText("urn:ogc:def:crs:EPSG::{0}".format(str(self.parent.iface.mapCanvas().mapRenderer().destinationCrs().postgisSrid())))
        self.ui.txtSrs.setVisible(True)
        self.ui.txtFeatureTypeTitle.setVisible(False)
        self.ui.txtFeatureTypeDescription.setVisible(False)
        self.ui.lblInfo.setText("FeatureTypes")
        self.ui.lblMessage.setText("")

        self.onlineresource = self.ui.txtUrl.text().strip()
        if len(self.onlineresource) == 0:
            QtGui.QMessageBox.critical(self, "OnlineResource Error", "Not a valid OnlineResource!")
            return

        if "?" in self.onlineresource:
            request = "{0}{1}".format(self.onlineresource, self.fix_acceptversions(self.onlineresource, "&"))
        else:
            request = "{0}{1}".format(self.onlineresource, self.fix_acceptversions(self.onlineresource, "?"))

        self.logMessage(request)

        capabilities = HTTPAuthDownloader(self)
        capabilities.download(self.processCapabilities, request)
        capabilities.show()


    def processCapabilities(self, buf):
        # process Response
        root = ElementTree.fromstring(buf)
        if self.is_wfs20_capabilties(root):
            # WFS 2.0 Namespace
            nswfs = "{http://www.opengis.net/wfs/2.0}"
            nsxlink = "{http://www.w3.org/1999/xlink}"
            nsows = "{http://www.opengis.net/ows/1.1}"
            # GetFeature OnlineResource
            for target in root.findall("{0}OperationsMetadata/{0}Operation".format(nsows)):
                if target.get("name") == "GetFeature":
                    for subtarget in target.findall("{0}DCP/{0}HTTP/{0}Get".format(nsows)):
                        getfeatureurl = subtarget.get("{0}href".format(nsxlink))
                        if not "?" in getfeatureurl:
                            self.onlineresource = getfeatureurl
                        else:
                            self.onlineresource = getfeatureurl[:getfeatureurl.find("?")]
                            self.vendorparameters = getfeatureurl[getfeatureurl.find("?"):].replace("?", "&")
            for target in root.findall("{0}FeatureTypeList/{0}FeatureType".format(nswfs)):
                for name in target.findall("{0}Name".format(nswfs)):
                    self.ui.cmbFeatureType.addItem(name.text,name.text)
                    featuretype = wfs20lib.FeatureType(name.text)
                    if ":" in name.text:
                        nsmap = self.get_namespace_map(buf)
                        for prefix in nsmap:
                            if prefix == name.text[:name.text.find(":")]:
                                featuretype.setNamespace(nsmap[prefix])
                                featuretype.setNamespacePrefix(prefix)
                                break
                    for title in target.findall("{0}Title".format(nswfs)):
                        featuretype.setTitle(title.text)
                    for abstract in target.findall("{0}Abstract".format(nswfs)):
                        featuretype.setAbstract(abstract.text)
                    for metadata_url in target.findall("{0}MetadataURL".format(nswfs)):
                        featuretype.setMetadataUrl(metadata_url.get("{0}href".format(nsxlink)))
                    for bbox in target.findall("{0}WGS84BoundingBox".format(nsows)):
                        for lowercorner in bbox.findall("{0}LowerCorner".format(nsows)):
                            featuretype.setWgs84BoundingBoxEast(lowercorner.text.split(' ')[0])
                            featuretype.setWgs84BoundingBoxSouth(lowercorner.text.split(' ')[1])
                        for uppercorner in bbox.findall("{0}UpperCorner".format(nsows)):
                            featuretype.setWgs84BoundingBoxWest(uppercorner.text.split(' ')[0])
                            featuretype.setWgs84BoundingBoxNorth(uppercorner.text.split(' ')[1])
                    self.featuretypes[name.text] = featuretype
                    self.querytype="adhocquery"
        else:
            self.ui.lblMessage.setText("")

        self.update_ui()


    #Process ListStoredQueries-Request
    def listStoredQueries(self):
        self.init_variables()
        self.ui.cmdGetFeature.setEnabled(False);
        self.ui.cmbFeatureType.clear()
        self.ui.frmExtent.hide()
        self.ui.frmParameter.show()
        self.layout_reset()
        self.ui.cmdMetadata.setVisible(False)
        self.ui.cmdExtent.setVisible(False)
        self.ui.lblCount.setVisible(False)
        self.ui.txtCount.setText("")
        self.ui.txtCount.setVisible(False)
        self.ui.lblSrs.setVisible(False)
        self.ui.txtSrs.setVisible(False)
        self.ui.txtFeatureTypeTitle.setVisible(False)
        self.ui.txtFeatureTypeDescription.setVisible(False)
        self.ui.lblInfo.setText("StoredQueries")
        self.ui.lblMessage.setText("")

        # self.onlineresource = self.ui.txtUrl.text().trimmed()
        if not self.onlineresource:
            QtGui.QMessageBox.critical(self, "OnlineResource Error", "Not a valid OnlineResource!")
            return
        if "?" in self.onlineresource:
            request = "{0}&service=WFS&version=2.0.0&request=DescribeStoredQueries".format(self.onlineresource)
        else:
            request = "{0}?service=WFS&version=2.0.0&request=DescribeStoredQueries".format(self.onlineresource)
        request += self.vendorparameters
        if self.ui.chkAuthentication.isChecked():
            self.setup_urllib2(request, self.ui.txtUsername.text().strip(), self.ui.txtPassword.text().strip())
        else:
            self.setup_urllib2(request, "", "")

        self.logMessage(request)

        procedures = HTTPAuthDownloader(self)
        procedures.download(self.processStoredProcedures, request)
        procedures.show()


    def processStoredProcedures(self, buf):
        # process Response
        root = ElementTree.fromstring(buf)
        # WFS 2.0 Namespace
        namespace = "{http://www.opengis.net/wfs/2.0}"
        # check correct Rootelement
        if root.tag == "{0}DescribeStoredQueriesResponse".format(namespace):
            for target in root.findall("{0}StoredQueryDescription".format(namespace)):
                self.ui.cmbFeatureType.addItem(target.get("id"),target.get("id"))
                lparameter = []
                for parameter in target.findall("{0}Parameter".format(namespace)):
                    lparameter.append(wfs20lib.StoredQueryParameter(parameter.get("name"), parameter.get("type")))
                storedquery = wfs20lib.StoredQuery(target.get("id"), lparameter)
                for title in target.findall("{0}Title".format(namespace)):
                    storedquery.setTitle(title.text)
                for abstract in target.findall("{0}Abstract".format(namespace)):
                    storedquery.setAbstract(abstract.text)
                self.storedqueries[target.get("id")] = storedquery
                self.querytype="storedquery" #R
        else:
            QtGui.QMessageBox.critical(self, "Error", "Not a valid DescribeStoredQueries-Response!")

        self.update_ui()


    # Process GetFeature-Request
    def getFeature(self):
        self.logMessage("getFeature() begin")
        self.ui.lblMessage.setText("Please wait while downloading!")
        if self.querytype == "storedquery":
            query_string = "?service=WFS&request=GetFeature&version=2.0.0&STOREDQUERY_ID={0}".format(self.ui.cmbFeatureType.currentText())
            storedquery = self.storedqueries[self.ui.cmbFeatureType.currentText()]
            lparameter = storedquery.getStoredQueryParameterList()
            for i in range(len(lparameter)):
                if not lparameter[i].isValidValue(self.parameter_lineedits[i].text().strip()):
                    QtGui.QMessageBox.critical(self, "Validation Error", lparameter[i].getName() + ": Value validation failed!")
                    self.ui.lblMessage.setText("")
                    return
                query_string+= "&{0}={1}".format(lparameter[i].getName(),self.parameter_lineedits[i].text().strip())
        else :
            # FIX
            featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]
            if len(self.bbox) < 1:
                query_string = "?service=WFS&request=GetFeature&version=2.0.0&srsName={0}&typeNames={1}".format(self.ui.txtSrs.text().strip(), self.ui.cmbFeatureType.currentText())
            else:
                query_string = "?service=WFS&request=GetFeature&version=2.0.0&srsName={0}&typeNames={1}&bbox={2}".format(self.ui.txtSrs.text().strip(), self.ui.cmbFeatureType.currentText(), self.bbox)

            if len(featuretype.getNamespace()) > 0 and len(featuretype.getNamespacePrefix()) > 0:
                #query_string += "&namespace=xmlns({0}={1})".format(featuretype.getNamespacePrefix(), urllib.quote(featuretype.getNamespace(),""))
                query_string += "&namespaces=xmlns({0},{1})".format(featuretype.getNamespacePrefix(), urllib.quote(featuretype.getNamespace(),""))

            if len(self.ui.txtCount.text().strip()) > 0:
                query_string+= "&count={0}".format(self.ui.txtCount.text().strip())
            # /FIX

        query_string+=self.vendorparameters

        resolvedepth = self.settings.value("/Wfs20Client/resolveDepth")
        if resolvedepth:
            query_string+="&resolvedepth={0}".format(resolvedepth)

        self.logMessage(self.onlineresource + query_string)

        layername="wfs{0}".format(''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(6)))

        window = ECPDownloader("https://dyfi.cobwebproject.eu/idp/profile/SAML2/SOAP/ECP", self)
        window.download(self.processFeatureCollection, self.onlineresource + query_string, self.get_temppath("{0}.gml".format(layername)))
        window.show()
        
        self.logMessage("getFeature() end")

    def processFeatureCollection(self, file):
        self.logMessage("processFeatureCollection() begin")

        # Parse and check only small files
        try:
            root = ElementTree.parse(str(file.fileName())).getroot()
            if not self.is_empty_response(root):
                self.logMessage("load_vector_layer(" + str(file.fileName()) + "," + self.ui.cmbFeatureType.currentText())
                self.load_vector_layer(str(file.fileName()), self.ui.cmbFeatureType.currentText())
            else:
                self.logMessage("0 Features returned!")
                QtGui.QMessageBox.information(self, "Information", "0 Features returned!")
                self.ui.lblMessage.setText("")

        except ParseError:
            self.logMessage("XML Parser Error")
            QtGui.QMessageBox.information(self, "Information", "XML Parser Error")
            self.unlock_ui()
            self.ui.lblMessage.setText("")
        
        self.unlock_ui()
        self.logMessage("processFeatureCollection() end")




    
    """
    ############################################################################################################################
    # UI
    ############################################################################################################################
    """

    # UI: Update SSL-Warning
    def check_url(self, url):
        if (url.startswith("https")):
            self.ui.lblWarning.setVisible(True)
        else:
            self.ui.lblWarning.setVisible(False)


    # UI: Update Parameter-Frame
    def update_ui(self):

        if self.querytype == "adhocquery":
            featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]

            if featuretype.getTitle():
                if len(featuretype.getTitle()) > 0:
                    self.ui.txtFeatureTypeTitle.setVisible(True)
                    self.ui.txtFeatureTypeTitle.setPlainText(featuretype.getTitle())
                else:
                    self.ui.txtFeatureTypeTitle.setVisible(False)
            else:
                self.ui.txtFeatureTypeTitle.setVisible(False)

            if featuretype.getAbstract():
                if len(featuretype.getAbstract()) > 0:
                    self.ui.txtFeatureTypeDescription.setVisible(True)
                    self.ui.txtFeatureTypeDescription.setPlainText(featuretype.getAbstract())
                else:
                    self.ui.txtFeatureTypeDescription.setVisible(False)
            else:
                self.ui.txtFeatureTypeDescription.setVisible(False)

            self.show_metadata_button(True)
            self.show_extent_button(True)
            self.ui.cmdGetFeature.setEnabled(True)
            self.ui.lblMessage.setText("")

        if self.querytype == "storedquery":
            storedquery = self.storedqueries[self.ui.cmbFeatureType.currentText()]

            if storedquery.getTitle():
                if len(storedquery.getTitle()) > 0:
                    self.ui.txtFeatureTypeTitle.setVisible(True)
                    self.ui.txtFeatureTypeTitle.setPlainText(storedquery.getTitle())
                else:
                    self.ui.txtFeatureTypeTitle.setVisible(False)
            else:
                self.ui.txtFeatureTypeTitle.setVisible(False)
            if storedquery.getAbstract():
                if len(storedquery.getAbstract()) > 0:
                    self.ui.txtFeatureTypeDescription.setVisible(True)
                    self.ui.txtFeatureTypeDescription.setPlainText(storedquery.getAbstract())
                else:
                    self.ui.txtFeatureTypeDescription.setVisible(False)
            else:
                self.ui.txtFeatureTypeDescription.setVisible(False)

            self.ui.cmdGetFeature.setEnabled(True)
            self.ui.lblMessage.setText("")
            self.layout_reset()
            for parameter in storedquery.getStoredQueryParameterList():
                self.layout_add_parameter(parameter)


    # UI: Update Extent-Frame
    def update_extent_frame(self):
        if self.ui.chkExtent.isChecked():
            canvas=self.parent.iface.mapCanvas()
            ext=canvas.extent()
            self.ui.txtExtentWest.setText('%s'%ext.xMinimum())
            self.ui.txtExtentEast.setText('%s'%ext.xMaximum())
            self.ui.txtExtentNorth.setText('%s'%ext.yMaximum())
            self.ui.txtExtentSouth.setText('%s'%ext.yMinimum())

            if (epsglib.isAxisOrderLatLon(self.ui.txtSrs.text().strip())):
                self.bbox='%s'%ext.yMinimum() + "," + '%s'%ext.xMinimum() + "," + '%s'%ext.yMaximum() + "," + '%s'%ext.xMaximum() + ",{0}".format(self.ui.txtSrs.text().strip())
            else:
                self.bbox='%s'%ext.xMinimum() + "," + '%s'%ext.yMinimum() + "," + '%s'%ext.xMaximum() + "," + '%s'%ext.yMaximum() + ",{0}".format(self.ui.txtSrs.text().strip())
        else:
            self.ui.txtExtentWest.setText("")
            self.ui.txtExtentEast.setText("")
            self.ui.txtExtentNorth.setText("")
            self.ui.txtExtentSouth.setText("")
            self.bbox=""

    # UI: Update Main-Frame / Enable|Disable Authentication
    def update_authentication(self):
        if not self.ui.chkAuthentication.isChecked():
            self.ui.frmMain.setGeometry(QtCore.QRect(10,90,501,551))
            self.ui.txtUsername.setVisible(False)
            self.ui.txtPassword.setVisible(False)
            self.ui.lblUsername.setVisible(False)
            self.ui.lblPassword.setVisible(False)
            self.resize(516, 648)
        else:
            self.ui.frmMain.setGeometry(QtCore.QRect(10,150,501,551))
            self.ui.txtUsername.setVisible(True)
            self.ui.txtPassword.setVisible(True)
            self.ui.lblUsername.setVisible(True)
            self.ui.lblPassword.setVisible(True)
            self.resize(516, 704)

    # GridLayout reset (StoredQueries)
    def layout_reset(self):
        for qlabel in self.parameter_labels:
            self.ui.gridLayout.removeWidget(qlabel)
            qlabel.setParent(None) # http://www.riverbankcomputing.com/pipermail/pyqt/2008-March/018803.html

        for qlineedit in self.parameter_lineedits:
            self.ui.gridLayout.removeWidget(qlineedit)
            qlineedit.setParent(None) # http://www.riverbankcomputing.com/pipermail/pyqt/2008-March/018803.html

        del self.parameter_labels[:]
        del self.parameter_lineedits[:]
        self.columnid = 0


    # GridLayout addParameter (StoredQueries)
    def layout_add_parameter(self, storedqueryparameter):
        qlineedit = QtGui.QLineEdit()
        qlabelname = QtGui.QLabel()
        qlabelname.setText(storedqueryparameter.getName())
        qlabeltype = QtGui.QLabel()
        qlabeltype.setText(storedqueryparameter.getType().replace("xsd:", ""))
        self.ui.gridLayout.addWidget(qlabelname, self.columnid, 0)
        self.ui.gridLayout.addWidget(qlineedit, self.columnid, 1)
        self.ui.gridLayout.addWidget(qlabeltype, self.columnid, 2)
        self.columnid = self.columnid + 1
        self.parameter_labels.append(qlabelname)
        self.parameter_labels.append(qlabeltype)
        self.parameter_lineedits.append(qlineedit)
        # newHeight = self.geometry().height() + 21
        # self.resize(self.geometry().width(), newHeight)


    def lock_ui(self):
        self.ui.cmdGetCapabilities.setEnabled(False)
        self.ui.cmdListStoredQueries.setEnabled(False)
        self.ui.cmdGetFeature.setEnabled(False)
        self.ui.cmbFeatureType.setEnabled(False)
        self.show_metadata_button(False)
        self.show_extent_button(False)

    def unlock_ui(self):
        self.ui.cmdGetCapabilities.setEnabled(True)
        self.ui.cmdListStoredQueries.setEnabled(True)
        self.ui.cmdGetFeature.setEnabled(True)
        self.ui.cmbFeatureType.setEnabled(True)
        self.show_metadata_button(True)
        self.show_extent_button(True)

    def show_metadata_button(self, enabled):
        if enabled:
            if self.querytype == "adhocquery":
                featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]
                if featuretype.getMetadataUrl():
                    if len(featuretype.getMetadataUrl()) > 0:
                        self.ui.cmdMetadata.setEnabled(True)
                    else:
                        self.ui.cmdMetadata.setEnabled(False)
                else:
                    self.ui.cmdMetadata.setEnabled(False)
        else:
            self.ui.cmdMetadata.setEnabled(False)

    def show_extent_button(self, enabled):
        if enabled:
            if self.querytype == "adhocquery":
                featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]
                if featuretype.getWgs84BoundingBoxEast():
                    if featuretype.getWgs84BoundingBoxEast() > 0:
                        self.ui.cmdExtent.setEnabled(True)
                    else:
                        self.ui.cmdExtent.setEnabled(False)
                else:
                    self.ui.cmdExtent.setEnabled(False)
        else:
            self.ui.cmdExtent.setEnabled(False)


    def show_extent(self):
        featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]
        self.create_layer(featuretype)


    def create_layer(self, featuretype):
        layer = QgsVectorLayer("polygon?crs=epsg:4326&", featuretype.getName() + " (Extent)", "memory")
        QgsMapLayerRegistry.instance().addMapLayer(layer)

        e = featuretype.getWgs84BoundingBoxEast()
        s = featuretype.getWgs84BoundingBoxSouth()
        w = featuretype.getWgs84BoundingBoxWest()
        n = featuretype.getWgs84BoundingBoxNorth()

        wkt = "POLYGON((" + e + " " + s + "," + e + " " + n + "," + w + " " + n + "," + w + " " + s + "," + e + " " + s + "))"
        geom = QgsGeometry.fromWkt(wkt)
        feature = QgsFeature()
        feature.setGeometry(geom)

        features = [feature]
        layer.dataProvider().addFeatures(features)
        layer.updateExtents()
        layer.reload()
        self.parent.iface.mapCanvas().refresh()
        self.parent.iface.zoomToActiveLayer()


    def show_metadata(self):
        featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]
        xslfilename = os.path.join(plugin_path, "iso19139jw.xsl")

        html = self.xsl_transform(featuretype.getMetadataUrl(), xslfilename)

        if html:
            # create and show the dialog
            dlg = MetadataClientDialog()
            dlg.ui.wvMetadata.setHtml(html)
            # show the dialog
            dlg.show()
            result = dlg.exec_()
            # See if OK was pressed
            if result == 1:
                # do something useful (delete the line containing pass and
                # substitute with your code
                pass
        else:
            QtGui.QMessageBox.critical(self, "Metadata Error", "Unable to read the Metadata")



    """
    ############################################################################################################################
    # UTIL
    ############################################################################################################################
    """

    def logMessage(self, message):
        if globals().has_key('QgsMessageLog'):
            QgsMessageLog.logMessage(message, "Wfs20Client")

    def get_url(self):
        defaultwfs = self.settings.value("/Wfs20Client/defaultWfs")
        if defaultwfs:
            return defaultwfs
        else:
            return "http://geoserv.weichand.de:8080/geoserver/wfs"

    def get_temppath(self, filename):
        tmpdir = os.path.join(tempfile.gettempdir(),'wfs20client')
        if not os.path.exists(tmpdir):
            os.makedirs(tmpdir)
        tmpfile= os.path.join(tmpdir, filename)
        return tmpfile

    # Receive Proxy from QGIS-Settings
    def getProxy(self):
        if self.settings.value("/proxy/proxyEnabled") == "true":
            proxy = "{0}:{1}".format(self.settings.value("/proxy/proxyHost"), self.settings.value("/proxy/proxyPort"))

            if (request.startswith("https")):
                return urllib2.ProxyHandler({"https" : proxy})
            else:
                return urllib2.ProxyHandler({"http" : proxy})
        else:
            return urllib2.ProxyHandler({})


    # Setup urllib2 (Proxy)
    def setup_urllib2(self, request, username, password):
        opener = urllib2.build_opener(self.getProxy())
        urllib2.install_opener(opener)


    # XSL Transformation
    def xsl_transform(self, url, xslfilename):
        try:
            self.setup_urllib2(url, "", "")
            response = urllib2.urlopen(url, None, 10)
            encoding=response.headers['content-type'].split('charset=')[-1]
            xml_source = unicode(response.read(), encoding)
        except urllib2.HTTPError, e:
            QtGui.QMessageBox.critical(self, "HTTP Error", "HTTP Error: {0}".format(e.code))
        except urllib2.URLError, e:
            QtGui.QMessageBox.critical(self, "URL Error", "URL Error: {0}".format(e.reason))
        else:
            # load xslt
            xslt_file = QtCore.QFile(xslfilename)
            xslt_file.open(QtCore.QIODevice.ReadOnly)
            xslt = unicode(xslt_file.readAll())
            xslt_file.close()

            # xslt
            qry = QtXmlPatterns.QXmlQuery(QtXmlPatterns.QXmlQuery.XSLT20)
            qry.setFocus(xml_source)
            qry.setQuery(xslt)

            xml_target = qry.evaluateToString()
            return xml_target


    # WFS 2.0 UTILS

    # check for OWS-Exception
    def is_exception(self, root):
        for namespace in ["{http://www.opengis.net/ows}", "{http://www.opengis.net/ows/1.1}"]:
        # check correct Rootelement
            if root.tag == "{0}ExceptionReport".format(namespace):
                for exception in root.findall("{0}Exception".format(namespace)):
                    for exception_text in exception.findall("{0}ExceptionText".format(namespace)):
                        QtGui.QMessageBox.critical(self, "OWS Exception", "OWS Exception returned from the WFS:<br>"+ str(exception_text.text))
                        self.ui.lblMessage.setText("")
                return True
        return False


    # check for correct WFS version (only WFS 2.0 supported)
    def is_wfs20_capabilties(self, root):
        if self.is_exception(root):
            return False
        if root.tag == "{0}WFS_Capabilities".format("{http://www.opengis.net/wfs/2.0}"):
            return True
        if root.tag == "{0}WFS_Capabilities".format("{http://www.opengis.net/wfs}"):
            QtGui.QMessageBox.warning(self, "Wrong WFS Version", "This Plugin has dedicated support for WFS 2.0!")
            self.ui.lblMessage.setText("")
            return False
        QtGui.QMessageBox.critical(self, "Error", "Not a valid WFS GetCapabilities-Response!")
        self.ui.lblMessage.setText("")
        return False


    # Check for empty GetFeature result
    def is_empty_response(self, root):
        # deegree 3.2: numberMatched="unknown" does return numberReturned="0" instead of numberReturned="unknown"
        # https://portal.opengeospatial.org/files?artifact_id=43925
        if not root.get("numberMatched") == "unknown":
            # no Features returned?
            if root.get("numberReturned") == "0":
                return True
        return False


    # Hack to fix version/acceptversions Request-Parameter
    def fix_acceptversions(self, onlineresource, connector):
        return "{0}service=WFS&acceptversions=2.0.0&request=GetCapabilities".format(connector)


    # Determine namespaces in the capabilities (including non-used)
    def get_namespace_map(self, xml):
        nsmap = {}
        for i in [m.start() for m in re.finditer('xmlns:', xml)]:
            j = i + 6
            prefix = xml[j:xml.find("=", j)]
            k = xml.find("\"", j)
            uri = xml[k + 1:xml.find("\"", k + 1)]

            prefix = prefix.strip()
            # uri = uri.replace("\"","")
            uri = uri.strip()
            # text+= prefix + " " + uri + "\n"

            nsmap[prefix] = uri
        return nsmap


    def load_vector_layer(self, fileName, layername):
    
    # Configure OGR/GDAL GML-Driver
        resolvexlinkhref = self.settings.value("/Wfs20Client/resolveXpathHref")
        attributestofields = self.settings.value("/Wfs20Client/attributesToFields")
        
        if resolvexlinkhref and resolvexlinkhref == "true":
            gdal.SetConfigOption('GML_SKIP_RESOLVE_ELEMS', 'NONE')
        else:
            gdal.SetConfigOption('GML_SKIP_RESOLVE_ELEMS', 'ALL')
        
        if attributestofields and attributestofields == "true":
            gdal.SetConfigOption('GML_ATTRIBUTES_TO_OGR_FIELDS', 'YES')
        else:
            gdal.SetConfigOption('GML_ATTRIBUTES_TO_OGR_FIELDS', 'NO')
        
        
        vlayer = QgsVectorLayer(fileName, layername, "ogr")
        vlayer.setProviderEncoding("UTF-8") #Ignore System Encoding --> TODO: Use XML-Header
        if not vlayer.isValid():
            QtGui.QMessageBox.critical(self, "Error", "Response is not a valid QGIS-Layer!")
            self.ui.lblMessage.setText("")
        else:
            self.ui.lblMessage.setText("")
            # QGIS 1.8, 1.9
            if hasattr(QgsMapLayerRegistry.instance(), "addMapLayers"):
                QgsMapLayerRegistry.instance().addMapLayers([vlayer])
            # QGIS 1.7
            else:
                QgsMapLayerRegistry.instance().addMapLayer(vlayer)
                self.parent.iface.zoomToActiveLayer()


class ECPDownloader(QProgressDialog):
    def __init__(self, idp_url, parent=None):
        QProgressDialog.__init__(self, parent)
        
        self.setWindowTitle("HTTPAuthdownloader")
        self.resize(self.size().width()*2, self.size().height())
        
        self.idp_url = idp_url
        
        self.contentLength = None
        
        self.jar = QNetworkCookieJar()
        
        self.manager = QNetworkAccessManager()
        self.manager.setCookieJar(self.jar)
        
        self.canceled.connect(self.cancelDownload)

    def replyMetaChanged(self):
        self.logMessage("replyMetaChanged()")
        self.contentLength = self.reply.header(QNetworkRequest.ContentLengthHeader)

    def download(self, finishFunction, url, filename, data=None):
        self.logMessage("download()")
        self.finishFunction = finishFunction
        self.url = url
        self.filename = filename
        
        self.manager.finished.connect(self.downloadToFile)

        self.request = QNetworkRequest(QUrl(url))
        self.request.setRawHeader("PAOS", "ver='urn:liberty:paos:2003-08';'urn:oasis:names:tc:SAML:2.0:profiles:SSO:ecp'")
        self.request.setRawHeader("Accept", "text/xml; application/vnd.paos+xml")
        
        if data == None:
            self.reply = self.manager.get(self.request)
        else:
            self.reply = self.manager.post(self.request, data)
        
        self.reply.metaDataChanged.connect(self.replyMetaChanged)
        self.reply.downloadProgress.connect(self.updateDataReadProgress)
        self.reply.error.connect(self.processError)
        
        self.setMinimum(0)
        self.setMaximum(0)
        self.logMessage("Starting download for URL: " + self.url)
        self.show()

    def processError(self, error):
        self.logMessage("processError()")
        self.logMessage("%s: %s" % (error.__class__.__name__, error))
    
    def replyMetaChanged(self):
        self.logMessage("replyMetaChanged()")
        self.contentLength = self.reply.header(QNetworkRequest.ContentLengthHeader)
    
    def updateDataReadProgress(self, done, total):
        self.logMessage("updateDataReadProgress()")
        
        if self.contentLength:
            self.setMaximum(total)
        
        self.setValue(done)
    
    def downloadToFile(self, reply):
        self.logMessage("downloadFinished()")
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        
        if status == 200:
            self.contentType = self.reply.header(QNetworkRequest.ContentTypeHeader)
            self.contentType = unicode(self.contentType)
            self.logMessage("Content-Type: " + self.contentType)
            
        if (status == 200 and self.contentType == "application/vnd.paos+xml"):

            authnRequest = StringIO(self.reply.readAll())
            self.logMessage(authnRequest.buf)
            
            # get RelayState
            ix1 = authnRequest.buf.index("RelayState")
            ix1 = authnRequest.buf.index(">", ix1) + 1
            ix2 = authnRequest.buf.index("<", ix1)
            self.relayStateValue = authnRequest.buf[ix1:ix2]
            
            self.logMessage("RelayState: " + self.relayStateValue)
            
            # clear <Header> element
            ix1 = authnRequest.buf.index("Header>") + 7
            ix2 = authnRequest.buf.index("Header>", ix1) + 7
            authnRequest.buf = authnRequest.buf[:ix1-1] + '/' + authnRequest.buf[ix1-1:ix1] + authnRequest.buf[ix2:]
            
            self.logMessage("AuthnRequest to be send to IdP")
            self.logMessage(authnRequest.buf)
            
            idp = HTTPAuthDownloader(self)
            idp.download(self.processIdPResponse, self.idp_url, authnRequest.buf)


        else:
            if status in [301, 302]:
                redirect = reply.attribute(QNetworkRequest.RedirectionTargetAttribute)

                self.logMessage("Status Code" + str(status))
                self.logMessage("Following redirect to " + redirect.toString())
                self.request = QNetworkRequest(redirect)
                self.request.setRawHeader("PAOS", "ver='urn:liberty:paos:2003-08';'urn:oasis:names:tc:SAML:2.0:profiles:SSO:ecp'")
                self.request.setRawHeader("Accept", "text/xml; application/vnd.paos+xml")
                self.reply = self.manager.get(self.request)
                self.reply.metaDataChanged.connect(self.replyMetaChanged)
                self.reply.downloadProgress.connect(self.updateDataReadProgress)

            else:
                self.file = QFile(self.filename)
                self.file.open(QIODevice.WriteOnly)
                self.file.write(self.reply.readAll())
                self.file.close()
                self.reply.deleteLater()
                self.manager.deleteLater()
                self.close()
                self.finishFunction(self.file)
                self.close()

    def processIdPResponse(self, idpResponse):
        self.logMessage("AuthnResponse received from the IdP")
        self.logMessage(idpResponse)
                
        # extract ACSUrl from the AuthnResponse
        ix1 = idpResponse.index("AssertionConsumerServiceURL=\"") + len("AssertionConsumerServiceURL=\"")
        ix2 = idpResponse.index("\"", ix1)
        acsUrl = idpResponse[ix1:ix2]
                
        self.logMessage("ACSURL: " + acsUrl)
                
        # Add RelayState to AuthnResponse
        ix1 = idpResponse.index("Header>")
        ix2 = ix1 - 1
        while not idpResponse[ix2:ix1].startswith("<"):
            ix2 -= 1
            prefix = None
            if idpResponse[ix2:ix1].endswith(":"):
                prefix = idpResponse[ix2 + 1:ix1 - 1]
            else:
                prefix = idpResponse[ix2 + 1:ix1]
          
        relayState = "<ecp:RelayState xmlns:ecp=\"urn:oasis:names:tc:SAML:2.0:profiles:SSO:ecp\" " + prefix + ":actor=\"http://schemas.xmlsoap.org/soap/actor/next\" " + prefix + ":mustUnderstand=\"1\">" + self.relayStateValue + "</ecp:RelayState>"
        pattern = "<" + prefix + ":Header>"
        replacement = "<" + prefix + ":Header>" + relayState
        idpResponse = idpResponse.replace(pattern, replacement)
            
        self.logMessage("AuthnResponse to be send to the SP")
        self.logMessage(idpResponse)
                
        self.logMessage("Sending AuthnResponse to the SP: " + acsUrl)
        self.request = QNetworkRequest(QUrl(acsUrl))
        self.request.setRawHeader("Content-Type", "application/vnd.paos+xml")
        self.reply = self.manager.post(self.request, idpResponse)


    def cancelDownload(self):
        self.logMessage("cancelDownload()")
        self.reply.abort()
        self.close()


    def logMessage(self, message):
        if globals().has_key('QgsMessageLog'):
            QgsMessageLog.logMessage(message, "ECPDownloader")

class HTTPAuthDownloader(QProgressDialog):
    def __init__(self, parent=None):
        QProgressDialog.__init__(self, parent)
        self.parent = parent
        
        self.setWindowTitle("HTTPAuthdownloader")
        self.resize(self.size().width()*2, self.size().height())
        
        self.contentLength = None
        
        self.jar = QNetworkCookieJar()
        
        self.manager = QNetworkAccessManager()
        self.manager.setCookieJar(self.jar)
        
        self.manager.finished.connect(self.downloadFinished)
        self.manager.authenticationRequired.connect(self.authenticate)
        self.canceled.connect(self.cancelDownload)
    
    def download(self, finishFunction, url, data=None):
        self.finishFunction = finishFunction
        self.url = url
        
        self.request = QNetworkRequest(QUrl(url))
        
        if data == None:
            self.reply = self.manager.get(self.request)
        else:
            self.reply = self.manager.post(self.request, data)
        
        self.reply.metaDataChanged.connect(self.replyMetaChanged)
        self.reply.downloadProgress.connect(self.updateDataReadProgress)
        self.reply.error.connect(self.processError)
        
        self.setMinimum(0)
        self.setMaximum(0)
        self.logMessage("Starting download for URL: " + self.url)
        self.show()
    
    
    def authenticate(self, reply, authenticator):
        url = unicode(reply.url().toString())
        realm = unicode(authenticator.realm())
        self.logMessage("HTTP auth required for realm: " + realm)
        
        user, password, status = self.http_authentication_callback(url, realm)
        
        if status == QDialog.Accepted:
            authenticator.setUser(user)
            authenticator.setPassword(password)
        else:
            self.logMessage("callback returned User Cancel")

    def processError(self, error):
        self.logMessage("%s: %s" % (error.__class__.__name__, error))
    
    def replyMetaChanged(self):
        self.logMessage("replyMetaChanged()")
        self.contentLength = self.reply.header(QNetworkRequest.ContentLengthHeader)
    
    def updateDataReadProgress(self, done, total):
        self.logMessage("updateDataReadProgress()")
        
        if self.contentLength:
            self.setMaximum(total)
        
        self.setValue(done)
    
    
    def downloadFinished(self, reply):
        self.logMessage("downloadFinished()")
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        redirect = reply.attribute(QNetworkRequest.RedirectionTargetAttribute)
        
        self.logMessage("Status Code" + str(status))
        if status in [301, 302]:
            self.logMessage("Following redirect to " + redirect.toString())
            self.request = QNetworkRequest(redirect)
            self.reply.abort()
            self.reply = self.manager.get(self.request)
            self.reply.downloadProgress.connect(self.updateDataReadProgress)
        elif status in [401, 500]:
            self.cancelDownload()
            self.parent.cancelDownload()
        else:
            self.reply.deleteLater()
            self.manager.deleteLater()
            self.close()
            buffer = StringIO(self.reply.readAll())
            self.finishFunction(buffer.buf)

    def cancelDownload(self):
        self.reply.abort()
        self.close()
    
    def http_authentication_callback(self, url, realm):
        return LoginBox.getUserPassword(realm, self)

    def logMessage(self, message):
        if globals().has_key('QgsMessageLog'):
            QgsMessageLog.logMessage(message, "HTTPAuthDownloader")


class LoginBox(QtGui.QDialog):
    def __init__(self, realm, parent = None):
        QtGui.QDialog.__init__(self, parent)
        
        self.setWindowTitle("HTTP Authentication")
        
        self.textName = QLineEdit(self)
        self.textName.setEchoMode(QLineEdit.Normal)
        
        self.textPass = QLineEdit(self)
        self.textPass.setEchoMode(QLineEdit.Password)
        
        self.realmText = QLineEdit(self)
        self.realmText.setText(realm)
        self.realmText.setReadOnly(True)
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.realmText)
        layout.addWidget(self.textName)
        layout.addWidget(self.textPass)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setMinimumSize(400, 200)
    
    @staticmethod
    def getUserPassword(realm, parent):
        dialog = LoginBox(realm, parent)
        result = dialog.exec_()
        return (dialog.textName.text(), dialog.textPass.text(), result == QDialog.Accepted)

