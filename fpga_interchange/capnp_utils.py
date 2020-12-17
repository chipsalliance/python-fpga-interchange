import capnp.lib.capnp

def get_module_from_id(capnp_id, parser=None):
    if parser is None:
        parser = capnp.lib.capnp._global_schema_parser

    return parser.modules_by_id[capnp_id]
