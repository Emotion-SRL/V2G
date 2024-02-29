from typing import Union, Dict
import canopen
import logging

logger = logging.getLogger(__name__)


class LocalNode(canopen.LocalNode):
    """canopen.LocalNode with PDO implementation:
    - Send on sync reception
    - Update OD on RPDO etc
    """

    def __init__(
        self,
        node_id: int,
        object_dictionary: Union[canopen.objectdictionary.ObjectDictionary, str],
    ):
        super().__init__(node_id, object_dictionary)
        self.pdo_data_store: Dict[int, Dict[int, bytes]] = {}
        self.pdo_config_callbacks = []

    def _on_sync(self, *args):
        """Transmit enabled TPDOs on sync reception"""
        for tpdo in self.tpdo.map.values():
            if tpdo.enabled:
                tpdo.transmit()

    def on_rpdo(self, mapobject):
        """Update internal data store on rpdo receive"""
        for obj in mapobject:
            # Set data in internal data store
            self.data_store.setdefault(obj.index, {})
            self.data_store[obj.index][obj.subindex] = bytes(obj.data)

    def _pdo_update_callback(self, index: int, subindex: int, od, data) -> None:
        """Callback on set data for updating values inside pdo"""
        # Set the according variable
        try:
            self.pdo_data_store[index][subindex].set_data(data)
        except KeyError as e:
            # logger.error(f"key error when trying to update {hex(index)} {hex(subindex)} of node {self.id}")
            pass
        except Exception as e:
            logger.error(f"error occured when trying to update PDO because {e}")

    def add_pdo_configuration_callback(self, callback):
        """Add a PDO configuration callback in particular
        this can be used to enable PDOs,change cob-ids configure mapping
        etc.
        Any of these callbacks will be called when the start() method is called
        """
        self.pdo_config_callbacks.append(callback)

    def start(self):
        # Add all the tpdo variables to the callback function
        self.add_write_callback(self._pdo_update_callback)
        # Subscribe to sync
        self.network.subscribe(0x80, self._on_sync)
        for callback in self.pdo_config_callbacks:
            callback()
        # Add callbacks for enabled RPDOs
        for rpdo in self.rpdo.map.values():
            if rpdo.enabled:
                logger.info(f"adding write callback for RPDO {hex(rpdo.cob_id)} of {self.id} ==> OD")
                rpdo.add_callback(self.on_rpdo)
        # Add calbacks for TPDOs
        logger.info(f"Adding write callbacks for OD ==> TPDOS of id : {self.id}")
        for pdo_map in self.tpdo.map.values():
            for od_var in pdo_map.map:
                self.pdo_data_store.setdefault(od_var.index, {})
                self.pdo_data_store[od_var.index][od_var.subindex] = od_var
        # ! important workaround before submiting a PR, when using receive_own_messages (for testing in particular)
        # if TPDO is enabled then pdo will subscribe to own message meaning that it can overwrite the value from OD.
        # the workaround consists in removing the TPDOs from subsription on network
        # !! Don't call .save() or .read() after this
        for tpdo in self.tpdo.map.values():
            if tpdo.enabled:
                logger.info(
                    f"removing {hex(tpdo.cob_id)} from pdo subscriptions to avoid over-writing existing data"
                )
                self.network.unsubscribe(tpdo.cob_id, tpdo.on_message)

    def stop(self):
        self.pdo.stop()
        self.nmt.stop_heartbeat()
