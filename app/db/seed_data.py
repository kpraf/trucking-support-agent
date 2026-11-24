"""Hand-picked reference data for the seed script.

Kept separate from seed.py so the lists are easy to review and edit.
Barangay names are real; street numbers, subdivisions, people, phone numbers
and shippers are all made up.
"""

FIRST_NAMES = [
    # common given names in Southern Tagalog
    "Juan",
    "Jose",
    "Mark",
    "John Paul",
    "Christian",
    "Jerome",
    "Rodel",
    "Ramil",
    "Arnel",
    "Jomar",
    "Kenneth",
    "Carlo",
    "Paolo",
    "Miguel",
    "Angelo",
    "Jayson",
    "Rommel",
    "Noel",
    "Efren",
    "Ronaldo",
    "Ariel",
    "Reynaldo",
    "Danilo",
    "Edgardo",
    "Joel",
    "Ryan",
    "Aldrin",
    "Maria",
    "Ma. Cristina",
    "Angelica",
    "Kristine",
    "Jessa",
    "Rowena",
    "Marites",
    "Lorna",
    "Gemma",
    "Liza",
    "Sheila",
    "Jocelyn",
    "Mary Grace",
    "Princess",
    "Camille",
    "Bea",
    "Patricia",
    "Ana Marie",
    "Rhea",
    "Lovely",
    "Joy",
    "Nenita",
    "Erlinda",
    "Rosalie",
    "Maricel",
    "Analyn",
    "Jennylyn",
    "Divina",
    "Cherry",
]

LAST_NAMES = [
    "Santos",
    "Reyes",
    "Cruz",
    "Bautista",
    "Ocampo",
    "Garcia",
    "Mendoza",
    "Torres",
    "Tomas",
    "Andrada",
    "Castillo",
    "Flores",
    "Villanueva",
    "Ramos",
    "Castro",
    "Rivera",
    "Aquino",
    "Navarro",
    "Salazar",
    "Mercado",
    "Dela Cruz",
    "De Guzman",
    "Pascual",
    "Manalo",
    "Gonzales",
    "Lopez",
    "Panganiban",
    "Macaraeg",
    "Dimaculangan",
    "Magbanua",
    "Evangelista",
    "Javier",
    "Soriano",
    "Valdez",
    "Hernandez",
    "Perez",
    "Aguilar",
    "Samonte",
    "Buenaventura",
    "Dizon",
    "Alcantara",
    "Sarmiento",
    "Velasco",
    "Umali",
    "Malabanan",
    "Dimapilis",
    "Cabrera",
    "Ilagan",
    "Belen",
    "Laurel",
    "Comia",
    "Ebron",
    "Pamintuan",
]

MOBILE_PREFIXES = [
    "0917",
    "0918",
    "0919",
    "0920",
    "0921",
    "0927",
    "0928",
    "0939",
    "0945",
    "0947",
    "0955",
    "0956",
    "0961",
    "0966",
    "0977",
    "0995",
    "0998",
    "0999",
]

# city -> (province, barangays)
CITIES = {
    "Calamba": ("Laguna", ["Real", "Parian", "Halang", "Canlubang", "Pansol", "Bucal", "Mayapa"]),
    "Santa Rosa": ("Laguna", ["Balibago", "Tagapo", "Dila", "Pooc", "Labas", "Macabling"]),
    "Biñan": ("Laguna", ["San Antonio", "Canlalay", "Malaban", "Santo Tomas", "Platero"]),
    "San Pedro": ("Laguna", ["Landayan", "Pacita I", "San Vicente", "Nueva", "Cuyab"]),
    "Cabuyao": ("Laguna", ["Banlic", "Mamatid", "Pulo", "Niugan", "Sala", "Marinig"]),
    "Los Baños": ("Laguna", ["Batong Malake", "Anos", "Bayog", "Maahas", "Mayondon"]),
    "San Pablo": ("Laguna", ["San Rafael", "Del Remedio", "San Francisco", "Santa Monica"]),
    "Santa Cruz": ("Laguna", ["Bagumbayan", "Pagsawitan", "Patimbao", "Santo Angel"]),
    "Dasmariñas": ("Cavite", ["Salitran", "Paliparan", "Sampaloc", "Burol", "Langkaan"]),
    "Bacoor": ("Cavite", ["Molino", "Niog", "Habay", "Talaba", "Panapaan"]),
    "Imus": ("Cavite", ["Anabu", "Bucandala", "Malagasang", "Pasong Buaya", "Tanzang Luma"]),
    "General Trias": ("Cavite", ["Manggahan", "Pasong Kawayan", "Santiago", "Tejero"]),
    "Silang": ("Cavite", ["Biga", "Lalaan", "Pooc", "Tartaria", "Puting Kahoy"]),
    "Tagaytay": ("Cavite", ["Kaybagal", "Silang Junction", "Maharlika", "Mendez Crossing"]),
    "Trece Martires": ("Cavite", ["Cabuco", "De Ocampo", "Lapidario", "Osorio"]),
    "Tanza": ("Cavite", ["Amaya", "Bagtas", "Daang Amaya", "Sahud Ulo"]),
    "Carmona": ("Cavite", ["Maduya", "Mabuhay", "Lantic", "Bancal"]),
}

# destination city -> hub that serves it
HUBS = {
    "Calamba": "Calamba Hub",
    "Los Baños": "Calamba Hub",
    "San Pablo": "Calamba Hub",
    "Santa Cruz": "Calamba Hub",
    "Cabuyao": "Calamba Hub",
    "Santa Rosa": "Santa Rosa Hub",
    "Biñan": "Santa Rosa Hub",
    "San Pedro": "Santa Rosa Hub",
    "Carmona": "Santa Rosa Hub",
    "Dasmariñas": "Dasmariñas Hub",
    "Silang": "Dasmariñas Hub",
    "Tagaytay": "Dasmariñas Hub",
    "General Trias": "Dasmariñas Hub",
    "Trece Martires": "Dasmariñas Hub",
    "Bacoor": "Imus Hub",
    "Imus": "Imus Hub",
    "Tanza": "Imus Hub",
}

SUBDIVISIONS = [
    "Villa Ligaya Homes",
    "Mabuhay Homes",
    "Sampaguita Village",
    "Greenfields Subdivision",
    "Bagong Pag-asa Village",
    "St. Joseph Village",
    "Lakeview Homes",
    "Palmera Heights",
    "Narra Park Subdivision",
    "Villa Esperanza",
    "Golden Meadows",
    "Lupang Pangarap Village",
]

STREETS = [
    "Rizal",
    "Mabini",
    "Bonifacio",
    "Luna",
    "Del Pilar",
    "Burgos",
    "Aguinaldo",
    "J.P. Laurel",
    "Sampaguita",
    "Ilang-Ilang",
    "Narra",
    "Acacia",
    "Kamagong",
    "Gumamela",
    "Quezon",
]

# shipper -> (origin city, [(item description, pieces)])
SHIPPERS = {
    "Tahanan Furniture Trading": (
        "Biñan",
        [
            ("3-seater sofa", 1),
            ("6-seater dining set", 7),
            ("queen-size bed frame", 3),
            ("wooden wardrobe cabinet", 2),
        ],
    ),
    "Mabuhay Hardware and Construction Supply": (
        "Calamba",
        [
            ("cement, 20 bags", 20),
            ("PVC pipes, 1 bundle", 1),
            ("floor tiles, 10 boxes", 10),
            ("paint, 5 gallons", 5),
        ],
    ),
    "Silangan Appliance Center": (
        "Dasmariñas",
        [
            ("2-door refrigerator", 1),
            ("front-load washing machine", 1),
            ("1.5HP window-type aircon", 1),
            ("55-inch LED TV", 1),
        ],
    ),
    "Kusina Pro Kitchen Equipment": (
        "Bacoor",
        [
            ("commercial gas range", 1),
            ("chest freezer", 1),
            ("stainless steel prep table", 2),
        ],
    ),
    "Luntian Garden Supplies": (
        "Silang",
        [
            ("potted plants, 12 pcs", 12),
            ("garden soil, 10 sacks", 10),
            ("garden set, 5 pcs", 5),
        ],
    ),
    "Bayanihan Bike Shop": (
        "Santa Rosa",
        [
            ("mountain bike", 1),
            ("e-bike", 1),
            ("bike parts, 1 box", 1),
        ],
    ),
    "Pinoy Gadget Hub": (
        "Imus",
        [
            ("desktop computer set", 3),
            ("inkjet printer", 1),
            ("24-inch monitor, 2 pcs", 2),
        ],
    ),
    "Aling Celia's Rattan Crafts": (
        "Los Baños",
        [
            ("rattan sala set", 4),
            ("rattan hamper set", 3),
        ],
    ),
    "Masagana Rice Trading": (
        "Cabuyao",
        [
            ("rice, 10 sacks (25 kg)", 10),
            ("rice, 5 sacks (50 kg)", 5),
        ],
    ),
    "Tibay Steel and Roofing": (
        "General Trias",
        [
            ("GI roofing sheets, 1 bundle", 1),
            ("steel bars, 1 bundle", 1),
        ],
    ),
    "Kalinisan Water Systems": (
        "San Pedro",
        [
            ("water dispenser", 1),
            ("water filtration unit", 2),
            ("water containers, 20 pcs", 20),
        ],
    ),
    "Ginhawa Mattress Depot": (
        "Tanza",
        [
            ("queen-size foam mattress", 1),
            ("double-deck bed with mattresses", 3),
        ],
    ),
    "Bukid Fresh Farm Supplies": (
        "San Pablo",
        [
            ("fertilizer, 8 sacks", 8),
            ("animal feeds, 10 sacks", 10),
        ],
    ),
    "Ilaw Lighting Center": (
        "Carmona",
        [
            ("LED panel lights, 2 boxes", 2),
            ("crystal chandelier", 1),
        ],
    ),
    "Sinag Solar Solutions": (
        "Tagaytay",
        [
            ("solar panel kit", 4),
            ("inverter and battery set", 2),
        ],
    ),
}

FAILED_ATTEMPT_NOTES = [
    "No one home to receive",
    "Receiver not reachable by phone",
    "Incomplete address, could not locate house",
    "Receiver refused, said item was not ordered",
    "Truck could not enter the subdivision gate",
    "Flooded road, could not pass",
]

ON_HOLD_NOTES = [
    "Held at hub: incomplete address",
    "Held at hub: receiver asked to hold",
    "Held at hub: shipper asked to hold",
    "Held at hub: truck under maintenance",
]

# How many of the 200 shipments get each status.
STATUS_COUNTS = {
    "booked": 30,
    "picked_up": 20,
    "at_hub": 35,
    "out_for_delivery": 20,
    "delivered": 55,
    "failed_attempt": 20,
    "on_hold": 12,
    "returned_to_shipper": 8,
}
