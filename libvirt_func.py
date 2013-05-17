# -*- coding: utf-8 -*-

import libvirt
from libvirt import libvirtError
import virtinst.util as util
from network.IPy import IP


def libvirt_conn(host):
    """

    Function for connect to libvirt host.
    Create exceptions and return if not connnected.

    """

    if host.conn_type == 'tcp':
        def creds(credentials, user_data):
            for credential in credentials:
                if credential[0] == libvirt.VIR_CRED_AUTHNAME:
                    credential[4] = host.login
                    if len(credential[4]) == 0:
                        credential[4] = credential[3]
                elif credential[0] == libvirt.VIR_CRED_PASSPHRASE:
                    credential[4] = host.passwd
                else:
                    return -1
            return 0

        flags = [libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_PASSPHRASE]
        auth = [flags, creds, None]
        uri = 'qemu+tcp://%s/system' % host.ipaddr
    if host.conn_type == 'ssh':
        uri = 'qemu+ssh://%s@%s:%s/system' % (host.login, host.ipaddr, host.ssh_port)

    try:
        if host.conn_type == 'tcp':
            conn = libvirt.openAuth(uri, auth, 0)
        if host.conn_type == 'ssh':
            conn = libvirt.open(uri)
        return conn
    except libvirt.libvirtError as e:
        return {'error': e.message}


def hard_accel_node(conn):
    """

    Check hardware acceleration.

    """

    import re
    xml = conn.getCapabilities()
    kvm = re.search('kvm', xml)
    if kvm:
        return True
    else:
        return False


def vds_get_node(conn):
    """

    Get all VM in host server

    """

    try:
        vname = {}
        for id in conn.listDomainsID():
            id = int(id)
            dom = conn.lookupByID(id)
            vname[dom.name()] = dom.info()[0]
        for id in conn.listDefinedDomains():
            dom = conn.lookupByName(id)
            vname[dom.name()] = dom.info()[0]
        return vname
    except libvirtError as e:
        add_error(e, 'libvirt')
        return "error"


def networks_get_node(conn):
    """

    Function return host server virtual networks.

    """

    virtnet = {}
    for network in conn.listNetworks():
        net = conn.networkLookupByName(network)
        status = net.isActive()
        virtnet[network] = status
    for network in conn.listDefinedNetworks():
        net = conn.networkLookupByName(network)
        status = net.isActive()
        virtnet[network] = status
    return virtnet


def storages_get_node(conn):
    """

    Function return host server storages.

    """

    storages = {}
    for storage in conn.listStoragePools():
        stg = conn.storagePoolLookupByName(storage)
        status = stg.isActive()
        storages[storage] = status
    for storage in conn.listDefinedStoragePools():
        stg = conn.storagePoolLookupByName(storage)
        status = stg.isActive()
        storages[storage] = status
    return storages


def node_get_info(conn):
    """

    Function return host server information: hostname, cpu, memory, ...

    """

    try:
        info = []
        xml_inf = conn.getSysinfo(0)
        info.append(conn.getHostname())
        info.append(conn.getInfo()[0])
        info.append(conn.getInfo()[2])
        info.append(util.get_xml_path(xml_inf, "/sysinfo/processor/entry[6]"))
        return info
    except libvirtError:
        return "error"


def memory_get_usage(conn):
    """

    Function return memory usage on node.

    """

    try:
        allmem = conn.getInfo()[1] * 1048576
        get_freemem = conn.getMemoryStats(-1, 0)
        if type(get_freemem) == dict:
            freemem = (get_freemem.values()[0] + get_freemem.values()[2] + get_freemem.values()[3]) * 1024
            percent = (freemem * 100) / allmem
            percent = 100 - percent
            memusage = (allmem - freemem)
        else:
            memusage = None
            percent = None
        return allmem, memusage, percent
    except libvirtError:
        return "error"


def cpu_get_usage(conn):
    """

    Function return cpu usage on node.

    """

    import time

    try:
        prev_idle = 0
        prev_total = 0
        cpu = conn.getCPUStats(-1, 0)
        if type(cpu) == dict:
            for num in range(2):
                    idle = conn.getCPUStats(-1, 0).values()[1]
                    total = sum(conn.getCPUStats(-1, 0).values())
                    diff_idle = idle - prev_idle
                    diff_total = total - prev_total
                    diff_usage = (1000 * (diff_total - diff_idle) / diff_total + 5) / 10
                    prev_total = total
                    prev_idle = idle
                    if num == 0:
                        time.sleep(1)
                    else:
                        if diff_usage < 0:
                            diff_usage = 0
        else:
            diff_usage = None
        return diff_usage
    except libvirtError as e:
        return e.message


def new_volume(storage, name, size):
    """

    Add new volume in storage

    """

    size = int(size) * 1073741824
    stg_type = util.get_xml_path(storage.XMLDesc(0), "/pool/@type")
    if stg_type == 'dir':
        name = name + '.img'
        alloc = 0
    else:
        alloc = size
    xml = """
        <volume>
            <name>%s</name>
            <capacity>%s</capacity>
            <allocation>%s</allocation>
            <target>
                <format type='qcow2'/>
            </target>
        </volume>""" % (name, size, alloc)
    storage.createXML(xml, 0)


def clone_volume(storage, img, new_img):
    """

    Function clone volume

    """

    stg_type = util.get_xml_path(storage.XMLDesc(0), "/pool/@type")
    if stg_type == 'dir':
        new_img = new_img + '.img'
    vol = storage.storageVolLookupByName(img)
    xml = """
        <volume>
            <name>%s</name>
            <capacity>0</capacity>
            <allocation>0</allocation>
            <target>
                <format type='qcow2'/>
            </target>
        </volume>""" % (new_img)
    storage.createXMLFrom(xml, vol, 0)


def images_get_storages(conn, storages):
    """

    Function return all images on all storages

    """

    import re
    disk = []
    for storage in storages:
        stg = conn.storagePoolLookupByName(storage)
        stg.refresh(0)
        for img in stg.listVolumes():
            if re.findall(".iso", img) or re.findall(".ISO", img):
                pass
            else:
                disk.append(img)
    return disk


def image_get_path(conn, vol, storages):
    """

    Function return volume path.

    """

    for storage in storages:
        stg = conn.storagePoolLookupByName(storage)
        for img in stg.listVolumes():
            if vol == img:
                vl = stg.storageVolLookupByName(vol)
                return vl.path()


def storage_get_info(storage):
    """

    Function return storage info.

    """

    if storage.info()[3] == 0:
        percent = 0
    else:
        percent = (storage.info()[2] * 100) / storage.info()[1]
    info = storage.info()
    info.append(int(percent))
    info.append(storage.isActive())
    xml = storage.XMLDesc(0)
    info.append(util.get_xml_path(xml, "/pool/@type"))
    info.append(util.get_xml_path(xml, "/pool/target/path"))
    info.append(util.get_xml_path(xml, "/pool/source/device/@path"))
    info.append(util.get_xml_path(xml, "/pool/source/format/@type"))
    return info


def new_storage_pool(conn, type_pool, name, source, target):
    """

    Function create storage pool.

    """

    xml = """
            <pool type='%s'>
            <name>%s</name>""" % (type_pool, name)

    if type_pool == 'logical':
        xml += """
              <source>
                <device path='%s'/>
                <name>%s</name>
                <format type='lvm2'/>
              </source>""" % (source, name)

    if type_pool == 'logical':
        target = '/dev/' + name

    xml += """
              <target>
                   <path>%s</path>
              </target>
            </pool>""" % (target)
    conn.storagePoolDefineXML(xml, 0)


def volume_get_info(storage):
    """

    Function return volume info.

    """

    volinfo = {}
    for name in storage.listVolumes():
        vol = storage.storageVolLookupByName(name)
        xml = vol.XMLDesc(0)
        size = vol.info()[1]
        format = util.get_xml_path(xml, "/volume/target/format/@type")
        volinfo[name] = size, format
    return volinfo


def new_network_pool(conn, name, forward, gw, netmask, dhcp):
    """

    Function create network pool.

    """

    xml = """
        <network>
            <name>%s</name>""" % (name)

    if forward == "nat" or "route":
        xml += """<forward mode='%s'/>""" % (forward)

    xml += """<bridge stp='on' delay='0' />
                <ip address='%s' netmask='%s'>""" % (gw, netmask)

    if dhcp[0] == '1':
        xml += """<dhcp>
                    <range start='%s' end='%s' />
                </dhcp>""" % (dhcp[1], dhcp[2])

    xml += """</ip>
        </network>"""
    conn.networkDefineXML(xml)


def network_get_info(network):
    """

    Function return network info.

    """

    info = []
    info.append(network.isActive())
    info.append(network.bridgeName())
    return info


def network_get_subnet(network):
    """

    Function return virtual network info: ip, netmask, dhcp, type forward.

    """

    ipv4 = []
    xml_net = network.XMLDesc(0)

    fw = util.get_xml_path(xml_net, "/network/forward/@mode")
    forwardDev = util.get_xml_path(xml_net, "/network/forward/@dev")

    if fw and forwardDev:
        ipv4.append([fw, forwardDev])
    else:
        ipv4.append(None)

    # Subnet block
    addrStr = util.get_xml_path(xml_net, "/network/ip/@address")
    netmaskStr = util.get_xml_path(xml_net, "/network/ip/@netmask")

    if addrStr and netmaskStr:
        netmask = IP(netmaskStr)
        gateway = IP(addrStr)
        network = IP(gateway.int() & netmask.int())
        ipv4.append(IP(str(network) + "/" + netmaskStr))
    else:
        ipv4.append(None)

    # DHCP block
    dhcpstart = util.get_xml_path(xml_net, "/network/ip/dhcp/range[1]/@start")
    dhcpend = util.get_xml_path(xml_net, "/network/ip/dhcp/range[1]/@end")

    if not dhcpstart or not dhcpend:
        pass
    else:
        ipv4.append([IP(dhcpstart), IP(dhcpend)])
    return ipv4


def snapshots_get_node(conn):
    """

    Function return all snaphots on node.

    """

    try:
        vname = {}
        for vm_id in conn.listDomainsID():
            vm_id = int(vm_id)
            dom = conn.lookupByID(vm_id)
            if dom.snapshotNum(0) != 0:
                vname[dom.name()] = dom.info()[0]
        for vm in conn.listDefinedDomains():
            dom = conn.lookupByName(vm)
            if dom.snapshotNum(0) != 0:
                vname[dom.name()] = dom.info()[0]
        return vname
    except libvirtError as e:
        return e.message


def snapshots_get_vds(vname):
    """

    Function return all vds snaphots.

    """

    from datetime import datetime
    try:
        snapshots = {}
        all_snapshot = vname.snapshotListNames(0)
        for snapshot in all_snapshot:
            snapshots[snapshot] = (datetime.fromtimestamp(int(snapshot)), vname.info()[0])
        return snapshots
    except libvirtError as e:
        return e.message


def snapshot_delete(vname, name_snap):
    """

    Function delete vds snaphots.

    """

    try:
        snap = vname.snapshotLookupByName(name_snap, 0)
        snap.delete(0)
    except libvirtError as e:
        return e.message


def snapshot_revert(vname, name_snap):
    """

    Function revert vds snaphots.

    """

    try:
        snap = vname.snapshotLookupByName(name_snap, 0)
        vname.revertToSnapshot(snap, 0)
    except libvirtError as e:
        return e.message


def vnc_get_port(conn, vname):
    """

    Function rever vds snaphots.

    """

    dom = conn.lookupByName(vname)
    port = util.get_xml_path(dom.XMLDesc(0), "/domain/devices/graphics/@port")
    return port