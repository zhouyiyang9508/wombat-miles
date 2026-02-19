"""Mock API responses for testing."""

ALASKA_RESPONSE = {
    "slices": [
        {
            "segments": [
                {
                    "departureStation": "SFO",
                    "arrivalStation": "LAX",
                    "departureTime": "2025-03-20T08:30:00-07:00",
                    "arrivalTime": "2025-03-20T10:05:00-07:00",
                    "publishingCarrier": {
                        "carrierCode": "AS",
                        "flightNumber": "1234"
                    },
                    "duration": 95,
                    "aircraft": "Boeing 737-900",
                    "amenities": ["Wi-Fi", "Power Outlets"]
                }
            ],
            "fares": {
                "saver_economy": {
                    "bookingCodes": ["X"],
                    "cabins": ["SAVER"],
                    "milesPoints": 5000,
                    "grandTotal": 5.60
                },
                "main_economy": {
                    "bookingCodes": ["Y"],
                    "cabins": ["MAIN"],
                    "milesPoints": 7500,
                    "grandTotal": 5.60
                },
                "first": {
                    "bookingCodes": ["F"],
                    "cabins": ["FIRST"],
                    "milesPoints": 15000,
                    "grandTotal": 5.60
                }
            }
        },
        {
            "segments": [
                {
                    "departureStation": "SFO",
                    "arrivalStation": "LAX",
                    "departureTime": "2025-03-20T14:00:00-07:00",
                    "arrivalTime": "2025-03-20T15:35:00-07:00",
                    "publishingCarrier": {
                        "carrierCode": "AS",
                        "flightNumber": "5678"
                    },
                    "duration": 95,
                    "aircraft": "Boeing 737 MAX 9",
                    "amenities": ["Wi-Fi"]
                }
            ],
            "fares": {
                "main_economy": {
                    "bookingCodes": ["Y"],
                    "cabins": ["MAIN"],
                    "milesPoints": 7500,
                    "grandTotal": 5.60
                },
                "first": {
                    "bookingCodes": ["F"],
                    "cabins": ["FIRST"],
                    "milesPoints": 20000,
                    "grandTotal": 5.60
                }
            }
        },
        {
            # Connection flight - should be skipped
            "segments": [
                {
                    "departureStation": "SFO",
                    "arrivalStation": "SEA",
                    "departureTime": "2025-03-20T06:00:00-07:00",
                    "arrivalTime": "2025-03-20T08:15:00-07:00",
                    "publishingCarrier": {"carrierCode": "AS", "flightNumber": "100"},
                    "duration": 135,
                    "aircraft": "Boeing 737-800",
                    "amenities": []
                },
                {
                    "departureStation": "SEA",
                    "arrivalStation": "LAX",
                    "departureTime": "2025-03-20T09:30:00-07:00",
                    "arrivalTime": "2025-03-20T12:00:00-07:00",
                    "publishingCarrier": {"carrierCode": "AS", "flightNumber": "200"},
                    "duration": 150,
                    "aircraft": "Boeing 737-800",
                    "amenities": []
                }
            ],
            "fares": {
                "main": {
                    "bookingCodes": ["Y"],
                    "cabins": ["MAIN"],
                    "milesPoints": 10000,
                    "grandTotal": 5.60
                }
            }
        }
    ]
}

ALASKA_EMPTY_RESPONSE = {"slices": []}
ALASKA_NO_SLICES_RESPONSE = {}

# International business class mock
ALASKA_INTL_RESPONSE = {
    "slices": [
        {
            "segments": [
                {
                    "departureStation": "SEA",
                    "arrivalStation": "NRT",
                    "departureTime": "2025-06-01T12:00:00-07:00",
                    "arrivalTime": "2025-06-02T14:30:00+09:00",
                    "publishingCarrier": {
                        "carrierCode": "JL",
                        "flightNumber": "69"
                    },
                    "duration": 630,
                    "aircraft": "Boeing 787-8",
                    "amenities": ["Wi-Fi", "Lie-flat Seats"]
                }
            ],
            "fares": {
                "business": {
                    "bookingCodes": ["J"],
                    "cabins": ["BUSINESS"],
                    "milesPoints": 55000,
                    "grandTotal": 86.20
                },
                "economy": {
                    "bookingCodes": ["Y"],
                    "cabins": ["COACH"],
                    "milesPoints": 25000,
                    "grandTotal": 86.20
                }
            }
        }
    ]
}


AEROPLAN_RESPONSE = {
    "data": {
        "airBoundGroups": [
            {
                "boundDetails": {
                    "segments": [
                        {"flightId": "FL001"}
                    ]
                },
                "airBounds": [
                    {
                        "availabilityDetails": [
                            {
                                "cabin": "business",
                                "bookingClass": "J"
                            }
                        ],
                        "prices": {
                            "milesConversion": {
                                "convertedMiles": {
                                    "base": 60000,
                                    "totalTaxes": 25000
                                },
                                "remainingNonConverted": {
                                    "currencyCode": "CAD"
                                }
                            }
                        }
                    },
                    {
                        "availabilityDetails": [
                            {
                                "cabin": "eco",
                                "bookingClass": "X"
                            }
                        ],
                        "prices": {
                            "milesConversion": {
                                "convertedMiles": {
                                    "base": 25000,
                                    "totalTaxes": 12500
                                },
                                "remainingNonConverted": {
                                    "currencyCode": "CAD"
                                }
                            }
                        }
                    }
                ]
            },
            {
                "boundDetails": {
                    "segments": [
                        {"flightId": "FL002"}
                    ]
                },
                "airBounds": [
                    {
                        "availabilityDetails": [
                            {
                                "cabin": "business",
                                "bookingClass": "C"
                            }
                        ],
                        "prices": {
                            "milesConversion": {
                                "convertedMiles": {
                                    "base": 70000,
                                    "totalTaxes": 28000
                                },
                                "remainingNonConverted": {
                                    "currencyCode": "CAD"
                                }
                            }
                        }
                    }
                ]
            },
            {
                # Connection - should be skipped
                "boundDetails": {
                    "segments": [
                        {"flightId": "FL003"},
                        {"flightId": "FL004"}
                    ]
                },
                "airBounds": [
                    {
                        "availabilityDetails": [
                            {"cabin": "eco", "bookingClass": "Y"}
                        ],
                        "prices": {
                            "milesConversion": {
                                "convertedMiles": {"base": 20000, "totalTaxes": 10000},
                                "remainingNonConverted": {"currencyCode": "CAD"}
                            }
                        }
                    }
                ]
            }
        ]
    },
    "dictionaries": {
        "flight": {
            "FL001": {
                "departure": {
                    "locationCode": "SFO",
                    "dateTime": "2025-06-01T09:00:00-07:00"
                },
                "arrival": {
                    "locationCode": "YYZ",
                    "dateTime": "2025-06-01T17:15:00-04:00"
                },
                "marketingAirlineCode": "AC",
                "marketingFlightNumber": "758",
                "aircraftCode": "789",
                "duration": 18900
            },
            "FL002": {
                "departure": {
                    "locationCode": "SFO",
                    "dateTime": "2025-06-01T17:30:00-07:00"
                },
                "arrival": {
                    "locationCode": "YYZ",
                    "dateTime": "2025-06-02T01:45:00-04:00"
                },
                "marketingAirlineCode": "AC",
                "marketingFlightNumber": "760",
                "aircraftCode": "333",
                "duration": 19500
            },
            "FL003": {
                "departure": {"locationCode": "SFO", "dateTime": "2025-06-01T06:00:00-07:00"},
                "arrival": {"locationCode": "YVR", "dateTime": "2025-06-01T08:30:00-07:00"},
                "marketingAirlineCode": "AC",
                "marketingFlightNumber": "100",
                "aircraftCode": "320",
                "duration": 9000
            },
            "FL004": {
                "departure": {"locationCode": "YVR", "dateTime": "2025-06-01T10:00:00-07:00"},
                "arrival": {"locationCode": "YYZ", "dateTime": "2025-06-01T17:30:00-04:00"},
                "marketingAirlineCode": "AC",
                "marketingFlightNumber": "200",
                "aircraftCode": "789",
                "duration": 16200
            }
        },
        "aircraft": {
            "789": "Boeing 787-9 Dreamliner",
            "333": "Airbus A330-300",
            "320": "Airbus A320"
        }
    },
    "errors": []
}

AEROPLAN_EMPTY_RESPONSE = {
    "data": {"airBoundGroups": []},
    "dictionaries": {"flight": {}, "aircraft": {}},
    "errors": []
}

AEROPLAN_ERROR_RESPONSE = {
    "data": None,
    "errors": [
        {"title": "No flights available for the requested route"}
    ]
}
