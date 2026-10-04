"""USGS Annual NLCD classes (valid classes only), including explicit land proxy.

Suitable-land is a descriptive non-water/non-ice/non-wetland class-area proxy,
not a buildability test. Developed, cultivated and forested land are retained.
"""
import numpy as np
from .spatial import raster_zonal


def prepare_land_cover_raster(source, cache_dir):
    """Reproject a categorical mosaic to EPSG:5070 with bounded GDAL memory.

    Native Annual NLCD mosaics use WGS84 Albers. Nearest-neighbor 30 m
    resampling preserves class labels; this is a documented derived raster,
    never a reassignment of the source CRS. Invalid classes stay invalid.
    """
    import json
    from pathlib import Path
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from .ingestion import file_digest, request_identity

    source = Path(source)
    digest = file_digest(source)
    method = {'output_crs':'EPSG:5070','resolution_m':30,'resampling':'nearest','method_version':'nlcd-warp-v1'}
    folder = Path(cache_dir) / request_identity(digest,'nlcd-warp-v1',method)
    target = folder / 'land_cover_5070.tif'
    manifest_path = folder / 'preparation_manifest.json'
    if manifest_path.exists() and target.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('source_sha256') != digest or manifest.get('output_sha256') != file_digest(target):
            raise ValueError('Prepared land-cover cache checksum mismatch')
        return target
    folder.mkdir(parents=True,exist_ok=True)
    partial = target.with_suffix('.tif.part')
    with rasterio.Env(GDAL_CACHEMAX=256_000_000), rasterio.open(source) as native:
        if native.crs is None or native.count != 1:
            raise ValueError('Native land-cover mosaic requires one categorical band and a CRS')
        transform,width,height = calculate_default_transform(native.crs,'EPSG:5070',native.width,native.height,*native.bounds,resolution=30)
        nodata = native.nodata if native.nodata is not None else 0
        profile = native.profile.copy()
        profile.update(driver='GTiff',crs='EPSG:5070',transform=transform,width=width,height=height,nodata=nodata,
                       tiled=True,blockxsize=512,blockysize=512,compress='deflate',BIGTIFF='IF_SAFER')
        with rasterio.open(partial,'w',**profile) as output:
            reproject(source=rasterio.band(native,1),destination=rasterio.band(output,1),
                      src_nodata=native.nodata,dst_nodata=nodata,resampling=Resampling.nearest,
                      warp_mem_limit=256,num_threads=1)
        source_crs = native.crs.to_wkt()
    partial.replace(target)
    manifest = dict(method,source_path=str(source.resolve()),source_sha256=digest,source_crs=source_crs,
                    output_path=str(target.resolve()),output_sha256=file_digest(target),output_bytes=target.stat().st_size,
                    warp_memory_limit_mb=256,nodata=nodata)
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return target

CLASSES={11:'water',12:'ice_snow',21:'developed_open',22:'developed_low',
         23:'developed_medium',24:'developed_high',31:'barren',41:'deciduous_forest',
         42:'evergreen_forest',43:'mixed_forest',52:'shrub',71:'grassland',
         81:'pasture',82:'cultivated',90:'woody_wetland',95:'emergent_wetland'}


def summarize_land_cover(path,geometry):
    z=raster_zonal(path,geometry,valid_values=set(CLASSES))
    a=z.valid_area_m2
    result={f'land_cover_{name}_frac':z.class_area(code)/a if a else np.nan for code,name in CLASSES.items()}
    result['nlcd_coverage_frac']=z.coverage_frac
    result['nlcd_observed_area_km2']=a/1e6 if a else np.nan
    result['nlcd_water_area_km2']=z.class_area(11)/1e6 if a else np.nan
    result['nlcd_land_area_km2']=(a-z.class_area(11))/1e6 if a else np.nan
    suitable=sum(z.class_area(c) for c in CLASSES if c not in {11,12,90,95})
    result['potentially_suitable_land_frac']=suitable/a if a else np.nan
    result['suitable_land_area_km2']=suitable/1e6 if a else np.nan
    return result
