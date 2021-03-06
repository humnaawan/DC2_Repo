from __future__ import with_statement
import argparse
import os
import numpy as np
import gzip
import h5py

from lsst.sims.catUtils.exampleCatalogDefinitions import PhoSimCatalogPoint
from lsst.sims.catalogs.definitions import InstanceCatalog
from lsst.sims.catalogs.decorators import cached
from lsst.sims.utils import arcsecFromRadians

from GCRCatSimInterface import PhoSimDESCQA, bulgeDESCQAObject, diskDESCQAObject


class MaskedPhoSimCatalogPoint(PhoSimCatalogPoint):

    disable_proper_motion = False

    min_mag = None

    column_outputs = ['prefix', 'uniqueId', 'raPhoSim', 'decPhoSim', 'maskedMagNorm', 'sedFilepath',
                      'redshift', 'gamma1', 'gamma2', 'kappa', 'raOffset', 'decOffset',
                      'spatialmodel', 'internalExtinctionModel',
                      'galacticExtinctionModel', 'galacticAv', 'galacticRv']

    protoDc2_half_size = 2.5*np.pi/180.

    @cached
    def get_maskedMagNorm(self):
        raw_norm = self.column_by_name('phoSimMagNorm')
        if self.min_mag is None:
            return raw_norm
        return np.where(raw_norm<self.min_mag, self.min_mag, raw_norm)

    @cached
    def get_inProtoDc2(self):
        ra_values = self.column_by_name('raPhoSim')
        ra = np.where(ra_values < np.pi, ra_values, ra_values - 2.*np.pi)
        dec = self.column_by_name('decPhoSim')
        return np.where((ra > -self.protoDc2_half_size) &
                        (ra < self.protoDc2_half_size) &
                        (dec > -self.protoDc2_half_size) &
                        (dec < self.protoDc2_half_size), 1, None)

    def column_by_name(self, colname):
        if (self.disable_proper_motion and
            colname in ('properMotionRa', 'properMotionDec',
                        'radialVelocity', 'parallax')):
            return np.zeros(len(self.column_by_name('raJ2000')), dtype=np.float)
        return super(MaskedPhoSimCatalogPoint, self).column_by_name(colname)


class BrightStarCatalog(PhoSimCatalogPoint):

    min_mag = None

    @cached
    def get_isBright(self):
        raw_norm = self.column_by_name('phoSimMagNorm')
        return np.where(raw_norm<self.min_mag, raw_norm, None)

class PhoSimDESCQA_ICRS(PhoSimDESCQA):
    catalog_type = 'phoSim_catalog_DESCQA_ICRS'

    column_outputs = ['prefix', 'uniqueId', 'raJ2000', 'decJ2000',
                      'phoSimMagNorm', 'sedFilepath',
                      'redshift', 'gamma1', 'gamma2', 'kappa',
                      'raOffset', 'decOffset',
                      'spatialmodel', 'majorAxis', 'minorAxis',
                      'positionAngle', 'sindex',
                      'internalExtinctionModel', 'internalAv', 'internalRv',
                      'galacticExtinctionModel', 'galacticAv', 'galacticRv',]

    transformations = {'raJ2000': np.degrees,
                       'decJ2000': np.degrees,
                       'positionAngle': np.degrees,
                       'majorAxis': arcsecFromRadians,
                       'minorAxis': arcsecFromRadians}


class MaskedPhoSimCatalogPoint_ICRS(MaskedPhoSimCatalogPoint):
    catalog_type = 'masked_phoSim_catalog_point_ICRS'

    column_outputs = ['prefix', 'uniqueId', 'raJ2000', 'decJ2000',
                      'maskedMagNorm', 'sedFilepath',
                      'redshift', 'gamma1', 'gamma2', 'kappa',
                      'raOffset', 'decOffset',
                      'spatialmodel',
                      'internalExtinctionModel',
                      'galacticExtinctionModel', 'galacticAv', 'galacticRv',]

    transformations = {'raJ2000': np.degrees,
                       'decJ2000': np.degrees}

class BrightStarCatalog_ICRS(BrightStarCatalog):
    catalog_type = 'bright_star_catalog_point_ICRS'

    column_outputs = ['prefix', 'uniqueId', 'raJ2000', 'decJ2000',
                      'phoSimMagNorm', 'sedFilepath',
                      'redshift', 'gamma1', 'gamma2', 'kappa',
                      'raOffset', 'decOffset',
                      'spatialmodel',
                      'internalExtinctionModel',
                      'galacticExtinctionModel', 'galacticAv', 'galacticRv',]

    transformations = {'raJ2000': np.degrees,
                       'decJ2000': np.degrees}


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Generate an InstanceCatalog')
    parser.add_argument('--db', type=str,
                        default='minion_1016_sqlite_new_dithers.db',
                        help='path to the OpSim database to query')
    parser.add_argument('--descqa_cat_file', type=str,
                        default='proto-dc2_v2.0',
                        help='path to DESCQA catalog file')
    parser.add_argument('--out', type=str,
                        default='.',
                        help='directory where output will be written')
    parser.add_argument('--id', type=int, nargs='+',
                        default=None,
                        help='obsHistID to generate InstanceCatalog for (a list)')
    parser.add_argument('--disable_dithering', default=False,
                        action='store_true',
                        help='flag to disable dithering')
    parser.add_argument('--min_mag', type=float, default=10.0,
                        help='the minimum magintude for stars')
    parser.add_argument('--fov', type=float, default=2.0,
                        help='field of view radius in degrees')
    parser.add_argument('--enable_proper_motion', default=False,
                        action='store_true',
                        help='flag to enable proper motion')
    parser.add_argument('--minsource', type=int, default=100,
                        help='mininum number of objects in a trimmed instance catalog')
    parser.add_argument('--imsim_catalog', default=False, action='store_true',
                        help='flag to produce object catalog for imSim')
    args = parser.parse_args()

    obshistid_list = args.id
    opsimdb = args.db
    out_dir = args.out

    from lsst.sims.catUtils.utils import ObservationMetaDataGenerator

    if not os.path.exists(opsimdb):
        raise RuntimeError('%s does not exist' % opsimdb)

    obs_generator = ObservationMetaDataGenerator(database=opsimdb, driver='sqlite')

    from lsst.sims.catUtils.exampleCatalogDefinitions import PhoSimCatalogZPoint
    from lsst.sims.catUtils.exampleCatalogDefinitions import DefaultPhoSimHeaderMap
    from lsst.sims.catUtils.baseCatalogModels import StarObj
    from lsst.sims.utils import _getRotSkyPos
    import copy

    star_db = StarObj(database='LSSTCATSIM', host='fatboy.phys.washington.edu',
                      port=1433, driver='mssql+pymssql')

    if not os.path.exists(out_dir):
        os.mkdir(out_dir)

    phosim_header_map = copy.deepcopy(DefaultPhoSimHeaderMap)
    phosim_header_map['nsnap'] = 1
    phosim_header_map['vistime'] = 30.0
    phosim_header_map['camconfig'] = 1

    if args.imsim_catalog:
        StarInstanceCatalogClass = MaskedPhoSimCatalogPoint_ICRS
        BrightStarCatalogClass = BrightStarCatalog_ICRS
        PhoSimDESCQAClass = PhoSimDESCQA_ICRS
    else:
        StarInstanceCatalogClass = MaskedPhoSimCatalogPoint
        BrightStarCatalogClass = BrightStarCatalog
        PhoSimDESCQAClass = PhoSimDESCQA

    for obshistid in obshistid_list:

        obs_list = obs_generator.getObservationMetaData(obsHistID=obshistid,
                                                        boundType='circle',
                                                        boundLength=args.fov)

        obs = obs_list[0]
        if not args.disable_dithering:
            obs.pointingRA = np.degrees(obs.OpsimMetaData['randomDitherFieldPerVisitRA'])
            obs.pointingDec = np.degrees(obs.OpsimMetaData['randomDitherFieldPerVisitDec'])
            rotSky = _getRotSkyPos(obs._pointingRA, obs._pointingDec, obs,
                                   obs.OpsimMetaData['ditheredRotTelPos'])

            obs.rotSkyPos = np.degrees(rotSky)
            obs.OpsimMetaData['rotTelPos'] = obs.OpsimMetaData['ditheredRotTelPos']

        cat_name = os.path.join(out_dir,'phosim_cat_%d.txt' % obshistid)
        star_name = 'star_cat_%d.txt' % obshistid
        gal_name = 'gal_cat_%d.txt' % obshistid
        #agn_name = 'agn_cat_%d.txt' % obshistid

        cat = PhoSimCatalogPoint(star_db, obs_metadata=obs)
        cat.phoSimHeaderMap = phosim_header_map
        with open(cat_name, 'w') as output:
            cat.write_header(output)
            output.write('minsource %i\n' % args.minsource)
            output.write('includeobj %s.gz\n' % star_name)
            output.write('includeobj %s.gz\n' % gal_name)
            #output.write('includeobj %s.gz\n' % agn_name)

        star_cat = StarInstanceCatalogClass(star_db, obs_metadata=obs,
                                            cannot_be_null=['inProtoDc2'])
        star_cat.phoSimHeaderMap = phosim_header_map
        bright_cat = BrightStarCatalogClass(star_db, obs_metadata=obs, cannot_be_null=['isBright'])
        star_cat.min_mag = args.min_mag
        star_cat.disable_proper_motion = not args.enable_proper_motion
        bright_cat.min_mag = args.min_mag

        from lsst.sims.catalogs.definitions import parallelCatalogWriter
        cat_dict = {}
        cat_dict[os.path.join(out_dir, star_name)] = star_cat
        cat_dict[os.path.join(out_dir, 'bright_stars_%d.txt' % obshistid)] = bright_cat
        parallelCatalogWriter(cat_dict, chunk_size=100000, write_header=False)

        db_bulge = bulgeDESCQAObject(args.descqa_cat_file)
        cat = PhoSimDESCQAClass(db_bulge, obs_metadata=obs,
                                cannot_be_null=['hasBulge'])
        cat.write_catalog(os.path.join(out_dir, gal_name), chunk_size=100000,
                          write_header=False)

        db_disk = diskDESCQAObject(args.descqa_cat_file)
        cat = PhoSimDESCQAClass(db_disk, obs_metadata=obs,
                                cannot_be_null=['hasDisk'])
        cat.write_catalog(os.path.join(out_dir, gal_name), chunk_size=100000,
                          write_mode='a', write_header=False)

        for orig_name in (star_name, gal_name):
            full_name = os.path.join(out_dir, orig_name)
            with open(full_name, 'rb') as input_file:
                with gzip.open(full_name+'.gz', 'wb') as output_file:
                    output_file.writelines(input_file)
            os.unlink(full_name)
