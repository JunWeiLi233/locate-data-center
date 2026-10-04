"""Native categorical mosaics must be reprojected without inventing classes."""
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from dc_locator.geography.sources import nlcd


def test_prepare_land_cover_preserves_categories_nodata_and_verifies_cache(tmp_path):
    native = tmp_path / 'native.tif'
    crs = '+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23 +lon_0=-96 +datum=WGS84 +units=m +no_defs'
    values = np.tile(np.array([11,31,0,95],dtype='uint8'),(4,1))
    with rasterio.open(native,'w',driver='GTiff',height=4,width=4,count=1,dtype='uint8',crs=crs,transform=from_origin(0,1000000,30,30),nodata=0) as ds:
        ds.write(values,1)
    prepared = nlcd.prepare_land_cover_raster(native,tmp_path/'cache')
    with rasterio.open(prepared) as ds:
        assert ds.crs.to_epsg() == 5070
        assert ds.transform.a == 30 and ds.transform.e == -30
        assert set(np.unique(ds.read(1))) <= {0,11,31,95}
        assert ds.nodata == 0
    manifest = json.loads((prepared.parent/'preparation_manifest.json').read_text())
    assert manifest['resampling'] == 'nearest'
    assert manifest['source_crs'] != manifest['output_crs']
    assert manifest['source_sha256'] and manifest['output_sha256']
    assert nlcd.prepare_land_cover_raster(native,tmp_path/'cache') == prepared
    with prepared.open('ab') as handle:
        handle.write(b'changed')
    with pytest.raises(ValueError,match='cache checksum'):
        nlcd.prepare_land_cover_raster(native,tmp_path/'cache')
