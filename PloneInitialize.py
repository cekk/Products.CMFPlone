from Products.ExternalMethod.ExternalMethod import manage_addExternalMethod
from Products.SiteAccess.SiteRoot import manage_addSiteRoot
from Products.SiteAccess.AccessRule import manage_addAccessRule

from AccessControl import User
from App.Extensions import getObject
from App.Common import package_home

import string
import glob 
import OFS.Application
import os
import sys
import zLOG

DEBUG = 0

def log(message, summary='', severity=0):
    zLOG.LOG('Plone Database Init', severity, summary, message)

from ConfigParser import ConfigParser

# grab the old initilalize...
old_initialize = OFS.Application.initialize
global out

def go(app):
    """ Initialize the ZODB with Plone """
    old_initialize(app)
    out = []
    # make sure that anything we have done so
    # far is committed, in case anything goes 
    # wrong later
    get_transaction().commit()
    
    # nothing no error at all should
    # stop the creation of the db
    # that would truly suck
    try: 
        _go(app)
    except:
        # if anything went wrong do an abort
        get_transaction().abort()
        out.append('Database init failed miserably [%s, %s]' % _get_error())

    if DEBUG and out:
        # only log if we have something to say
        # and are in DEBUG mode
        log('\n'.join(out)+'\n')

def _get_error():
    type, value = sys.exc_info()[:2]
    return str(type), str(value)

def _go(app):
    filename = 'plone.ini'
    filename = os.path.join(package_home(globals()), filename)

    # not the best
    try:
        fh = open(filename, 'r')
        cfg = ConfigParser()
        cfg.readfp(fh)
        fh.close()
    except IOError: 
        # no file found
        return

    # read the config file and find a million excuses
    # why we shouldnt do this...
    try:
        pid = cfg.get('databaseSetup', 'name')
        usernm  = cfg.get('databaseSetup', 'user')
        productList = cfg.get('databaseSetup', 'products').split(',')
        create = cfg.getint('databaseSetup', 'create')
        skinList = cfg.get('databaseSetup', 'skins').split(',')
    except ConfigParser.NoSectionError:
        # no section name databaseSetup
        out.append("NoSectionError when parsing config file")
        return
    except AttributeError:
        # no attribute named 
        out.append("AttributeError when parsing config file")
        return

    # ok if create in that file is set to 0, then we dont continue
    if not create:
        out.append("Config file found, but create set to 0")
        return

    oids = app.objectIds()

    # these are the two set elements...
    eid = 'accessRule.py'
    sid = 'SiteRoot'

    # 1. Create the admin user given the access file
    acl_users = getattr(app, "acl_users")

    # ugh oh well...
    try:
        if usernm not in acl_users.getUserNames():
            # read the file and add in
            # inituser is created by the installer
            info = User.readUserAccessFile('inituser')
            if info:
                out.append(str(info))
                acl_users._doAddUser(info[0], info[1], ('manage',), [])
                out.append("Added admin user")
                # important, get that user in there!
                get_transaction().commit()
            else:
                out.append("No inituser file found")
    except IOError: 
        out.append("Adding admin user failed [%s, %s]" %  _get_error())

    # 2 .now get that user, it could be that one already exists
    user = acl_users.getUser('admin').__of__(acl_users)
    if not user:
        out.append("Getting user failed [%s, %s]" %  _get_error())
    else:
        out.append("Gotten the admin user")

    # 3. now create the access rule
    if eid not in oids:
        # this is the actual access rule
        out.append("Added external method")
        manage_addExternalMethod(app, 
                                                  eid, 
                                                  'Plone Access Rule', 
                                                  'accessRule', 
                                                  'accessRule')
        # this sets the access rule
        out.append("Set as access rule")
        manage_addAccessRule(app, eid)
        if user:
            getattr(app, eid).changeOwnership(user)

    # 4. actually add in Plone
    if pid not in oids:
        # this import is potentially time-consuming so it's done 
        # as late as possible (benefits the way tests are loading).
        from Products.CMFPlone.Portal import manage_addSite
        out.append("Added Plone")
        manage_addSite(app, 
                   pid, 
                   title='Portal', 
                   description='',
                   create_userfolder=1,
                   email_from_address='postmaster@localhost',
                   email_from_name='Portal Administrator',
                   validate_email=0,
                   custom_policy='Default Plone',
                   RESPONSE=None)
        if user:
            getattr(app, pid).changeOwnership(user, recursive=1)

    # 5. adding the site root in
    plone = getattr(app, pid)
    if sid not in plone.objectIds():
        out.append("Added Site Root")
        manage_addSiteRoot(plone)
        if user:
            getattr(plone, sid).changeOwnership(user)
  
    # 6. add in products
    ids = [ x['id'] for x in plone.portal_quickinstaller.listInstallableProducts(skipInstalled=1) ]
    qit.installProducts(ids)
    
    # 6.1 patch up the products
    # CMF Collector is a very bad product
    # import workflow
    plone.portal_workflow.manage_importObject('collector_issue_workflow.zexp')
    cbt = plone.portal_workflow._chains_by_type
    cbt['Collector Issue'] = ('collector_issue_workflow',)

    # 7. add in skins
    # go and install the skins...
#    sk = plone.portal_migration._getWidget('Skin Setup')
#    sk.addItems(sk.available())   

    # 7.1 patch up the skins
    # Plone is a bad product
#    skins = plone.portal_skins.getSkinSelections()
#    for skin in skins:
#        path = plone.portal_skins.getSkinPath(skin)
#        path = map(string.strip, string.split(path,','))
#        path.insert(1, 'plone_3rdParty/CMFCollector')
#        plone.portal_skins.addSkinSelection(skin, ','.join(path))
    # Sigh, ok now CMFCollector should be in the path

    # 8. add in the languages
    sk = plone.portal_migration._getWidget('Localizer Language Setup')
    sk.addItems(sk.available())       
    
    # 9. commit
    get_transaction().commit()

    # and stop this happening again
    cfg.set('databaseSetup', 'create', 0)
    fh = open(filename, 'w')
    cfg.write(fh)
    out.append("Changed config file, set create = 0")
    fh.close()
    out.append("Finished")

# patch away!
OFS.Application.initialize = go
