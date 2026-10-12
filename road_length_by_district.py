# -*- coding: utf-8 -*-
"""
Extract selected road type, calculate length in km, and summarize by district.

Outputs:
1. Matching road line features with a calculated length_km field.
2. A non-spatial district summary table with segment count, total length (km),
   minimum, maximum, and average segment length for each district.

Install in QGIS: Processing Toolbox > Scripts > Create New Script, paste/save
as road_length_by_district.py, then refresh the Scripts provider.
Input must be a line layer with geometry and a district attribute.
"""

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterString,
    QgsProcessingParameterFeatureSink,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsDistanceArea,
    QgsWkbTypes,
    QgsFeatureSink,
)


class RoadLengthByDistrict(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    ROAD_FIELD = "ROAD_FIELD"
    SEARCH_VALUE = "SEARCH_VALUE"
    DISTRICT_FIELD = "DISTRICT_FIELD"
    OUTPUT_ROADS = "OUTPUT_ROADS"
    OUTPUT_STATS = "OUTPUT_STATS"

    def tr(self, string):
        return QCoreApplication.translate("RoadLengthByDistrict", string)

    def createInstance(self):
        return RoadLengthByDistrict()

    def name(self):
        return "road_length_by_district"

    def displayName(self):
        return self.tr("Extract Road Type + Length Statistics by District")

    def group(self):
        return self.tr("Road Network Tools")

    def groupId(self):
        return "road_network_tools"

    def shortHelpString(self):
        return self.tr(
            "Select a road line layer, the field containing the road type/name, a search value, "
            "and the district field. The algorithm extracts matching roads, calculates each "
            "segment's length in kilometres, and creates a district-wise summary table with "
            "segment count, total length, minimum, maximum, and average length. Search is a "
            "case-insensitive substring match. Example: field ref + NH; district field DISTRICT."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Input road line layer"), [QgsProcessing.TypeVectorLine]
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ROAD_FIELD,
            self.tr("Field containing road type/name (e.g. ref, name, highway)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Any,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.SEARCH_VALUE,
            self.tr("Road type/value to find (e.g. NH, SH, Expressway, primary)"),
            defaultValue="NH",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DISTRICT_FIELD,
            self.tr("District name/code field"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Any,
        ))
        # Let QGIS assign its standard temporary-output destination by default.
        # Explicit TEMPORARY_OUTPUT defaults can fail to populate output controls
        # in some QGIS versions / script-provider contexts.
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_ROADS,
            self.tr("Output: matching roads with length_km"),
            QgsProcessing.TypeVectorLine,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_STATS,
            self.tr("Output: district-wise statistics table"),
            QgsProcessing.TypeVector,
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise Exception("Could not read the input road layer.")
        road_field = self.parameterAsString(parameters, self.ROAD_FIELD, context)
        search_value = self.parameterAsString(parameters, self.SEARCH_VALUE, context).strip()
        district_field = self.parameterAsString(parameters, self.DISTRICT_FIELD, context)

        if source.wkbType() == QgsWkbTypes.NoGeometry:
            raise Exception("Input must be a road line layer with geometry; a plain CSV without geometry cannot be measured.")
        if not search_value:
            raise Exception("Enter a road type or name to search for.")

        fields = source.fields()
        road_idx = fields.indexFromName(road_field)
        district_idx = fields.indexFromName(district_field)
        if road_idx < 0:
            raise Exception("Road field '{}' was not found.".format(road_field))
        if district_idx < 0:
            raise Exception("District field '{}' was not found.".format(district_field))

        out_fields = QgsFields()
        for field in fields:
            out_fields.append(field)
        length_name = "length_km"
        existing_names = {f.name().lower() for f in fields}
        if length_name.lower() in existing_names:
            length_name = "calc_length_km"
        out_fields.append(QgsField(length_name, QVariant.Double, "double", 20, 6))

        road_sink, road_dest = self.parameterAsSink(
            parameters, self.OUTPUT_ROADS, context, out_fields,
            source.wkbType(), source.sourceCrs()
        )
        if road_sink is None:
            raise Exception("Could not create the matching-roads output.")

        stats_fields = QgsFields()
        stats_fields.append(QgsField("district", QVariant.String, len=254))
        stats_fields.append(QgsField("road_segments", QVariant.Int))
        stats_fields.append(QgsField("total_length_km", QVariant.Double, "double", 20, 6))
        stats_fields.append(QgsField("min_length_km", QVariant.Double, "double", 20, 6))
        stats_fields.append(QgsField("max_length_km", QVariant.Double, "double", 20, 6))
        stats_fields.append(QgsField("mean_length_km", QVariant.Double, "double", 20, 6))
        stats_sink, stats_dest = self.parameterAsSink(
            parameters, self.OUTPUT_STATS, context, stats_fields,
            QgsWkbTypes.NoGeometry, source.sourceCrs()
        )
        if stats_sink is None:
            raise Exception("Could not create the district statistics table.")

        distance = QgsDistanceArea()
        distance.setSourceCrs(source.sourceCrs(), context.transformContext())
        ellipsoid = context.project().ellipsoid()
        if not ellipsoid or ellipsoid == "NONE":
            ellipsoid = source.sourceCrs().ellipsoidAcronym()
        if ellipsoid and ellipsoid != "NONE":
            distance.setEllipsoid(ellipsoid)

        # Store the category statistics for each district.
        stats = {}
        total_features = source.featureCount()
        matched_count = 0
        overall_km = 0.0
        search_lower = search_value.casefold()

        for current, feature in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            value = feature.attribute(road_idx)
            if value is None or search_lower not in str(value).strip().casefold():
                continue
            geom = feature.geometry()
            if geom is None or geom.isNull() or geom.isEmpty():
                continue

            length_km = distance.measureLength(geom) / 1000.0
            out_feature = QgsFeature(out_fields)
            out_feature.setGeometry(geom)
            attrs = feature.attributes()
            attrs.append(length_km)
            out_feature.setAttributes(attrs)
            if not road_sink.addFeature(out_feature, QgsFeatureSink.FastInsert):
                raise Exception("Failed to write a matching road feature.")

            raw_district = feature.attribute(district_idx)
            district = "(NULL / Unassigned)" if raw_district is None or not str(raw_district).strip() else str(raw_district).strip()
            if district not in stats:
                stats[district] = {"count": 0, "sum": 0.0, "min": None, "max": None}
            row = stats[district]
            row["count"] += 1
            row["sum"] += length_km
            row["min"] = length_km if row["min"] is None else min(row["min"], length_km)
            row["max"] = length_km if row["max"] is None else max(row["max"], length_km)
            matched_count += 1
            overall_km += length_km

            if total_features:
                feedback.setProgress(int((current + 1) * 100 / total_features))

        for district, row in sorted(stats.items(), key=lambda item: item[0].casefold()):
            stat_feature = QgsFeature(stats_fields)
            stat_feature.setAttributes([
                district,
                row["count"],
                row["sum"],
                row["min"],
                row["max"],
                row["sum"] / row["count"] if row["count"] else None,
            ])
            if not stats_sink.addFeature(stat_feature, QgsFeatureSink.FastInsert):
                raise Exception("Failed to write district statistics.")

        feedback.pushInfo("---- Overall road length statistics ----")
        feedback.pushInfo("Search: '{}' contains '{}' (case-insensitive)".format(road_field, search_value))
        feedback.pushInfo("Matched road segments: {}".format(matched_count))
        feedback.pushInfo("Total length across all districts: {:.3f} km".format(overall_km))
        feedback.pushInfo("---- District-wise statistics (Statistics by Categories style) ----")
        if not stats:
            feedback.pushInfo("No matching roads found. Check the road field and search value.")
        for district, row in sorted(stats.items(), key=lambda item: item[0].casefold()):
            mean = row["sum"] / row["count"] if row["count"] else 0
            feedback.pushInfo(
                "{} | segments: {} | total: {:.3f} km | min: {:.6f} km | max: {:.6f} km | mean: {:.6f} km".format(
                    district, row["count"], row["sum"], row["min"], row["max"], mean
                )
            )

        return {self.OUTPUT_ROADS: road_dest, self.OUTPUT_STATS: stats_dest}
