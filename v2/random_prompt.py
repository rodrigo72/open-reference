import random
import numpy as np
from scipy.stats import truncnorm
import colorsys
import os


anatomy_parts = {
    "Torso": {
        "Muscles": {
            "Pecs": [
                "Clavicular portion", "Infravicular fossa", "Sternocostal portion", 
                "Abdominal portion"
            ],
            "Shoulder muscles": [
                "Supraspinatus", "Infraspinatus", "Teres Minor", "Teres Major", "Serratus Anterior", 
                "Subscapularis"
            ],
            "Lower Back Muscles": [
                "Erector Spinae", "Latissimus Dorsi", "Serratus Posterior Inferior"
            ],
            "Obliques": [
                "Thoracic portion", "Flank Portion", "Internal Oblique" 
            ],
            "Upper Back muscles": [
                "Trapezius", "Rhomboid"
            ],
            "Abs": [
                "Rectus Abdominis", "Transversus Abdominis",
            ],
            "Neck muscles": [
                "Semispinalis Capitis", "Splenius Capitis", "Levator Scapulae", "Scalene Muscles", 
                "Sternocleidomastoideus", "Omohyoideus", "Sternohyoideus", "Mylohyoideus", 
                "Digastricus", "Platysma"
            ],
        },
        "Bones": {
            "Pelvis": [
                "Anterior superior iliac spine", "Iliac crest", "Anterior inferior iliac spine", "Sacrum",
                "Acetabulum", "Pubic tubercle", "Pubic symphysis", "Obturator foramen", "Ischial tuberosity", 
                "Pubic arch", " Ischium", "Coccyx", "Sacral triangle", "Posterior superior iliac spine"
            ],
            "Rib cage": [
                "Sternum", "True Ribs", "False Ribs", "Xiphoic process", "Thoracic arch"
            ],
            "Shoulder bones": [
                "Scapula", "Spine of the Scapula", "Acromion Process", "Coracoid Process", "Clavicle"
            ],
            "Spine": [
                "Cervical", "Thoracic", "Lumbar", "Sacral"
            ],
        },
        "Other": {
            "Breasts": None,
        }, 
        "Motion": {
            "Shoulders": [
                "Elevation", "Depression", "Retraction", "Protraction", "Lateral rotation", "Medial rotation",
                "Posterior tilting", "Anterior tilting"
            ],
            "Spine": [
                "Lateral bending", "Extension", "Flexion", "180º rotation"
            ]
        }
    },
    "Arms": {
        "Muscles": {
            "Triceps": [
                "Long head", "Lateral Head", "Medial Head", "Tendon"
            ],
            "Biceps": [
                "Coracobrachialis", "Brachialis", "Biceps Brachii"
            ],
            "Forearm muscles": {
                "Ridge muscles": [
                    "Extensor Carpi Radialis Longus", "Brachioradialis"
                ],
                "Extensors": [
                    "Extensor Carpi Radialis Brevis", "Extensor Digitorum", "Extensor Digiti Minimi",
                    "Extensor Carpi Ulnaris", "Anconeus", "Abductor Pollicis Longus", "Extensor Pollicis Brevis",
                    "Extensor Pollicis Longus"
                ],
                "Flexors": [
                    "Flexor Carpi Radialis", "Palmaris Longus", "Flexer Carpi Ulnaris", 
                    "Flexor Digitorum Superficialis", "Flexor Digitorum Profundus",
                    "Flexor Pollicis Longus", "Pronator Teres", "Bicipital Aponeurosis"
                ]
            },
            "Hand muscles": [
                "Thenar Eminence", "Abductor Pollicis Brevis", "Flexor Pollicis Brevis", "Opponens Pollicis",
                "Adductor Pollicis", "Hypothenar Eminence", "Carpal Ligament", "Opponens Digiti Minimi", 
                "Flexor Digiti Minimi Brevis", "Abductor Digiti Minimi", "Palmaris Brevis", 
                "First Dorsal Interosseous", "Lumbricals"
            ],
            "Deltoid": [
                "Anterior head", "Lateral head", "Posterior head"
            ]
        },
        "Bones": {
            "Hand bones": [
                "Carpals", "Metacarpals", "Phalanges"
            ],
            "Arm bones": [
                "Humerus", "Radius", "Ulna"
            ],
        },
        "Motion": {
            "Arms": [
                "Flextion", "Extension", "Abduction", "Adduction", "Supination", "Pronation", "Circumduction"
            ],
            "Hands": [
                "Opposition", "Dorsiflection", "Palmarflexion", "50º adduction", "20º abduction"
            ]
        }
    },
    "Legs": {
        "Muscles": {
            "Butt muscles": [
                "Gluteus maximus", "Gluteus medius"
            ],
            "Leg muscles": {
                "Thigh (Front)": [
                    "Rectus femoris", "Vastus lateralis", "Vastus medialis", "Sartorius"
                ],
                "Thigh (Back)": [
                    "Biceps femoris", "Semitendinosus", "Semimembranosus"
                ],
                "Lower Leg (Front)": [
                    "Tibialis anterior"
                ],
                "Lower Leg (Back & Side)": [
                    "Gastrocnemius", "Soleus", "Fibularis longus"
                ]
            },
            "Feet muscles": [
                "Extensor digitorum brevis", "Abductor hallucis", "Abductor digiti minimi"
            ]
        },
        "Bones": {
            "Leg bones": [
                "Femur", "Patella", "Tibia", "Fibula"
            ],
            "Feet bones": [
                "Calcaneus", "Talus", "Metatarsals", "Phalanges"
            ]
        },
        "Motion": {
            "Legs": [
                "Flexion", "Extension", "Lateral rotation", "Medial rotation", "Adduction", "Abduction"
            ],
            "Feet": [
                "Inversion", "Eversion", "Dorsiflexion", "Plantarflextion"
            ]
        }
    }
}

perspective_variations = [
    "fish-eye lens", "two-point", "one-point", "three-point"
]

sex_variations = [
    "Male", "Female"
]

size_variations = [
    "small", "medium", "large"
]

face_parts = [
    "Eyes & Eyebrows", "Nose", "Ears", "Mouth", "Neck, Jaw & Chin", "Hair & Facial hair"
]

emotions_to_body_expression = {
    "primary": {
        "positive": {
            "surprise": [
                "raised eyebrows", "open mouth"
            ],
            "happiness": [
                "smiling", "relaxed posture", "open arms"
            ]
        },
        "negative": {
            "sadness": [
                "frowning", "slumped shoulders", "downcast eyes"
            ],
            "fear": [
                "wide eyes", "tensed body", "stepping back"
            ],
            "anger": [
                "furrowed brows", "clenched fists", "tense posture"
            ],
            "disgust": [
                "wrinkled nose", "turned-away head"
            ]
        }
    },
    "secondary": {
        "positive": {
            "excitement": [
                "bouncing on feet", "wide grin"
            ],
            "amusement": [
                "smirking", "raised eyebrows", "chuckling"
            ],
            "satisfaction": [
                "slow nod", "closed eyes with slight smile"
            ],
            "relief": [
                "deep exhale", "shoulders relaxing", "eyes softening"
            ],
            "love": [
                "soft gaze", "relaxed facial expression", "leaning in"
            ],
            "affection": [
                "gentle touch", "warm smile", "prolonged eye contact"
            ],
            "admiration": [
                "raised eyebrows", "slight smile", "nodding"
            ],
            "flirtation": [
                "playful smile", "tilting head", "sustained eue contact"
            ],
            "pride": [
                "chin raised", "chest puffed out", "hands on hips"
            ]
        },
        "negative": {
            "frustration": [
                "clenching fists", "rubbing forehead", "pacing"
            ],
            "annoyance": [
                "tapping fingers", "sighing", "eye-rolling"
            ],
            "impatiance": [
                "restless movements", "shifting weight", "checking time"
            ],
            "boredom": [
                "looking away", "yawning", "slouching"
            ],
            "jealousy": [
                "tense mouth", "darting glances", "arms crossed"
            ],
            "defensiveness": [
                "crossed arms", "pursed lips", "avoiding gaze"
            ],
            "suspicion": [
                "narrowed eyes", "tight lips", "arms crossed"
            ],
            "contempt": [
                "one-side smirk", "raised chin", "eye-rolling"
            ],
            "embarassment": [
                "blushing", "nervous laughter", "covering face"
            ],
            "guilt": [
                "avoiding eye contact", "fidgeting", "touching face"
            ],
            "shame": [
                "head lowered", "avoiding eye contact", "hunched shoulders"
            ],
            "doubt": [
                "raised one eyebrow", "slight forwn", "pursed lips"
            ],
            "resignation": [
                "slumped posture", "sighing", "slow blinking"
            ]
        }
    },
    "tertiary": {
        "social & cognitive": {
            "curiosity": [
                "leaning forward", "wide eyes", "slight head tilt"
            ],
            "confusion": [
                "furrowed brows", "head tilt", "pursed lips"
            ],
            "determination": [
                "clenched jaw", "focused eyes", "squared shoulders"
            ],
            "empathy": [
                "mirroring body language", "nodding", "soft eyes"
            ]
        },
        "fear-related & defensive": {
            "nervousness": [
                "fidgeting", "avoiding eye contact", "biting lip"
            ],
            "anxiety": [
                "rapid blinking", "wringin hands", "hunched shoulders"
            ]
        }
    },
    "quaternary": {
        "happiness & affection": {
            "euphoria": [
                "wide radiant smile", "eyes sparkling", "jumping"
            ],
            "nostalgia": [
                "soft smile with distant gaze", "slightly furrowed brows"
            ],
            "gratitude": [
                "warm smile", "slightly raised eyebrows", "hands over heart", "slight head bow"
            ],
            "serenity": [
                "gentle smile", "relaxed eyelids", "relaced shoulders"
            ]
        },
        "sadness & guilt": {
            "melancholy": [
                "downcast eyes", "faint frown", "slow blinking", "deep sighing"
            ],
            "regret": [
                "tense lips", "averted gaze", "restless hands", "rubbing forehead or temples"
            ],
            "remorse": [
                "deep frown", "downturned mouth", "brows drawn together", "hands covering face", "holding head"
            ],
            "homesickness": [
                "longing expression", "clutching personal objects"
            ]
        },
        "fear & anxiety": {
            "dread": [
                "wide or darting eyes", "slow hesitant movements", "backing away"
            ],
            "apprehension": [
                "tight jaw", "rubbing hands", "crossing arms"
            ],
            "alienation": [
                "lack of expression", "avoiding eye contact"
            ]
        },
        "anger & contempt": {
            "resentment": [
                "narrowed eyes", "stiff posture", "turning slightly away"
            ],
            "indignation": [
                "flared nostrils", "hands on hips", "pointing", "forceful gestures"
            ],
            "vindictiveness": [
                "smirk or cold stare", "leaning forward aggressively"
            ],
            "irritation": [
                "eyes rolling", "tapping fingers"
            ]
        },
        "surprise & confusion": {
            "awe": [
                "wide eyes", "slightly open mouth", "standing still", "hand on chest or covering mouth"
            ],
            "skepticism": [
                "one raised eyebrow", "lips pressed together", "tilted head"
            ],
            "disillusionment": [
                "tired expression", "shaking head", "looking away"
            ]
        }
    }
}

traditional_mediums = [
    "Watercolor", "Markers", "Coloured pencils", "Charcoal powder", "Charcoal pencils", "Graphite pencils",
    "Gouache", "Black Indian Ink", "Ink pens", "Oil pastel"
] 

exercises = {
    "Visual memory": [
"""Draw from memory
	- Look at it for 1 or 2 minutes, try to remember as much as you can about it
	- Hide your reference
	- Draw as much as you can from memory
	- Bring back your reference and check your accuracy
	- Try again (optional)""",
"""Draw from a different angle
	- Look at something and draw it from a different angle
	- You don't have to hide the reference for this one""",
"""Draw from memory and from a different angle
    -Start by looking at it for a few minutes
	- Draw it from memory and from a different angle
	- You can make it easier by starting with a 'study drawing', then put it away and draw it from memory and from a different angle""",
"""Draw from memory, from a different angle and change the proportions
    - Use reference as an inspiration to redesign and create your own thing""",
        "Drawing from a moving subject",
        "Draw the model in a different pose"
    ],
    "Natural way to draw": [
        "Contour drawing", "Gesture drawing", "Cross contours", "Potential gesture", "Flash pose", "Weight", "Modelled drawing",
        "Moving action", "Descriptive poses", "Reverse poses", "Daily composition", "Upside-down pose"
    ],
    "Other": [
        "Mannequinization", "Study with 3D Blender model", "Value study", "Colour study", "Hybrid | visual | structural style block-in"
    ],
    "Daily exercises": {
        "Level 1: Foundations": [
"""«Exercise 1 - Lines, Arcs and Waves 
    Goal: Develop control over different arm motions.»
    Instructions:
        Draw 3 sets of lines and 3 sets of arcs using 
        wrist, elbow, and arm movements.
        Go over each line 8 times.
        Bonus: Experiment with waves, go over multiple 
        times.""", 
"""«Exercise 2 - Point Coordination»
    Goal: Improve hand-eye coordination and line accuracy.
    Instructions:
        Place a point on the paper and draw straight lines
        through it.
        Experiment from multiple angles without rotating
        the page.
        Do this at a small, medium, and large scale.""",
"""«Exercise 3 - Ellipses»
    Goal: Practice drawing consistent circles and ellipses.
    Instructions:
        Draw straight horizontal lines across the page.
        Between the lines, draw evenly spaced ellipses.
        Change the angle and size of the ellipses.
        Draw a line of overlapping circles to improve 
        control and consistency.""",
"""«Exercise 4 - Parallel Ellipses»
    Goal: Practice creating consistent ellipses.
    Instructions:
        Draw a straight line.
        Draw ellipses of varying sizes along the line, 
        ensuring they remain perpendicular.""",
"""«Exercise 5 - Ribbons»
    Goal: Build fluidity and spatial awareness.
    Instructions:
        Draw a random curvy line.
        Repeat the line offset.
        Connect the lines parallel lines to create ribbons.
        Bonus: Experiment with 3D and perspective.""",
"""«Exercise 6 - Flattening Planes»
    Goal: Understand perspective transitions.
    Instructions:
        Start with a straight line.
        Progressively draw planes rotating toward the 
        viewer until it forms a regular square.
        Then rotate away from the viewer until it 
        returns to a line.
        Do this both vertically and horizontally.
        Repeat with circles."""
        ],
        "Level 2 - Exploring Forms and Perspective": [
"""«Exercise 7 - Extrusion»
    Goal: Visualize 3D forms from 2D shapes.
    Instructions:
        Draw a shape and offset it.
        Connect the shapes with lines to create a 3D effect.""", 
"""«Exercise 8 - Rotation»
    Goal: Master rotating basic forms.
    Instructions:
        Rotate basic shapes along a single axis.
        Add details like letters and rotate them with 
        the forms.""",
"""«Exercise 9 - Cube Grid»
    Goal: Visualize and draw cubes from multiple angles.
    Instructions:
        Create the two axes of the grid below.
        Use these axes to create cubes with the respective 
        horizontal and vertical rotation.
        Draw through the boxes.""",
"""«Exercise 10 - Box Stacking»
    Goal: Understand perspective and structure.
    Instructions:
        Stack uniform and rotated boxes.
        Expand the scope of your scene.""",
"""«Exercise 11 - Cylinders»
    Goal: Practice drawing cylinders.
    Instructions:
        Stack or arrange cylinders in space.""",
"""«Exercise 12 - Organic Forms»
    Goal: Develop a sense of volume and depth in shapes.
    Instructions:
        Draw blob-like shapes and add centerlines.
        Create contour lines to give the shapes depth.
        Optionally shade or branch the forms."""
        ],
        "Level 3: Combining and Manipulating Forms": [
"""«Exercise 13 - Stacking and Queuing»
    Goal: Understand perspective shifts in stacked forms
    Instructions:
        Line up forms vertically or horizontally.
        Imagine how perspective alters them.
        Use 1-point perspective for accuracy.""",
"""«Exercise 14 - Addition»
    Goal: Combine shapes to create unique forms.
    Instructions:
        Draw a basic form and create a unique form by 
        adding other forms to it.
        Rotate these forms and draw them from multiple angles.""",
"""«Exercise 15 - Bending»
    Goal: Experinemt with depth and distortion.
    Instructions:
        Bend and twist basic forms.
        Use overlaps to emphasize depth.""",
"""«Exercise 16 - Flat Textures»
    Goal: Practice creating gradients and patterns. 
          Drawing the viewer's attention to a particular area.
    Instructions:
        Create a rectangle and apply a texture that transitions
        from dark to light (or busy to minimal).
        Experiment with hatching, cross-hatching, patterns, 
        and more complex textures."""
        ],
        "Level 4: Advanced Visualization": [
"""«Exercise 17 - 3-box Figure»
    Goal: Simplify the human body into major masses.
    Instructions
        Using reference images, draw the head, ribcage, 
        and pelvis as boxes.
        Add stick limbs and block joints.
        To make this harder, ditch the reference images 
        and draw these poses from imagination.""",
"""«Exercise 18 - Subtraction»
    Goal: Visualize negative space and subtractive forms.
    Instructions:
        Draw a basic form and then construct another form 
        intersecting it.
        Visualize how the intersection affects volume.
        Start with subtracting a cube from another cube.
        Then use a cylinder, sphere, or cone to subtract 
        from a cube.""",
"""«Exercise 19 - Perspective Clusters»
    Goal: Combine forms in perspective to create complex 
          arrangements.
    Instructions:
        Draw clusters of forms using addition, subtraction, 
        and extrusion.
        Vary their size, shape, and orientation.""",
"""«Exercise 20 - Volume Mapping»
    Goal: Give volume and texture to an object.
    Instructions
        Use flat textures from Level 3.
        Apply them to organic forms to convey depth and texture.""",
"""«Exercise 21 - Copycat»
    Goal: Study and replicate techniques of a master.
    Instructions
        Copy a drawing by an artist you admire.
        Study their use of line, form and texture."""
        ],
        "Level 5 - Creative Exploration and Storytelling": [
"""«Exercise 22 - Mannequins»
    Instructions:
        Expand the 3-box figure with more accurate limb 
        volumes and other features.
        Start with references, then move on to drawing 
        from imagination.""",
"""«Exercise 23 - Object Visualization»
    Goal: Visualize and draw objects from unseen angles.
    Instructions:
        Draw an object from a different angle than observed.
        Imagine unseen parts to complete the drawing.""",
"""«Exercise 24 - POV Drawing»
    Goal: Practice drawing what you see.
    Instructions:
        Recreate scenes from your point of view.
        Focus on maitaining consistency and depth.""",
"""«Exercise 25 - Daily Highlight»
    Goal: Learn to draw from memory.
    Instructions:
        Pick a memorable moment from your day and draw it.""",
"""«Exercise 26 - The Comic Book» 
    Goal: Develop storytelling and consistency. This exercise 
    helps build your ability to not only tell stories, 
    but to design and create concept work on the fly.
    Instructions:
        Design a room and draw several shots, visualizing 
        different areas of the room while consistently 
        maintaining the forms that have been established."""
        ]
    }
}


textures = [
    "wood", "metal", "cloth", "glass", "plastic", "paper", "skin", "fur", "scales", "bone", "rock", "fire", "water"
]


restrictions = [
    "No eraser", "No planning / sketch", "No detailing", "Only negative space", "No straight lines", "No curves", 
    "Shading only / No outlines"
]

categories = [
    "Plants", "Entomology", "Bone structure", "Land animals", "Human figure", "The aviary", "Marine life", "Locomotives",
    "Automobiles", "Military", "Aviation", "Weapons", "Cloth", "Buildings", "Landscapes", "Textures"
]


def random_category():
    return random.choice(categories)


def random_paper_size(weights):
    return random.choices(["A3", "A4", "A5"], weights=weights, k=1)[0]


def random_restriction():
    return random.choice(restrictions)


def random_physique():
    return random.choices(["Lean", "Average", "Muscular", "Heavy"], weights=[0.2, 0.5, 0.25, 0.05], k=1)[0]


def random_sex():
    return random.choice(sex_variations)


def random_size():
    return random.choice(size_variations)


def random_anatomy(level):
    result = []
    anatomy_current = anatomy_parts.copy()
    for _ in range(level):
        if type(anatomy_current) == dict:
            if 'Motion' in anatomy_current:
                anatomy_current.pop('Motion')
            key = random.choice(list(anatomy_current.keys()))
            result.append(key)
            anatomy_current = anatomy_current[key]
        elif type(anatomy_current) == list:
            last = random.choice(anatomy_current)
            result.append(last)
            break
        else:
            break
    return result


def random_anatomy_motion():
    result = []
    anatomy_current = anatomy_parts.copy()
    for _ in range(5):
        if type(anatomy_current) == dict:
            if 'Motion' in anatomy_current:
                result.append('Motion')
                anatomy_current = anatomy_current['Motion']
            else:
                key = random.choice(list(anatomy_current.keys()))
                result.append(key)
                anatomy_current = anatomy_current[key]
        elif type(anatomy_current) == list:
            last = random.choice(anatomy_current)
            result.append(last)
            break
        else:
            break
    return result


def random_face_part():
    return random.choices(face_parts, weights=[0.2, 0.17, 0.14, 0.19, 0.14, 0.16], k=1)[0]


def random_emotion_to_body_expression(level):
    result = []
    emotion_current = emotions_to_body_expression.copy()
    for _ in range(level):
        if type(emotion_current) == dict:
            key = random.choice(list(emotion_current.keys()))
            result.append(key)
            emotion_current = emotion_current[key]
        elif type(emotion_current) == list:
            last = random.choice(emotion_current)
            result.append(last)
            break
        else:
            break
    return result


def random_traditional_mediums():
    return random.choice(traditional_mediums)


def random_exercise_old():
    exercise_type = random.choice(list(exercises.keys()))
    chosen_exercise = random.choice(exercises[exercise_type])
    return (exercise_type, chosen_exercise)


def random_exercise(level=3):
    result = []
    exercise_current = exercises.copy()
    for _ in range(level):
        if type(exercise_current) == dict:
            key = random.choice(list(exercise_current.keys()))
            result.append(key)
            exercise_current = exercise_current[key]
        elif type(exercise_current) == list:
            last = random.choice(exercise_current)
            result.append(last)
            break
        else:
            break
    return result


def random_daily_exercise(weights):
    daily_exercises = exercises['Daily exercises']
    level = random.choices(list(daily_exercises.keys()), weights=weights, k=1)[0]
    return level, random.choice(daily_exercises[level]) 


def random_texture():
    return random.choice(textures)


def random_lvl(func, levels=[1,2,3,4]):
    level = random.choice(levels)
    return func(level)


def random_direction():
    azimuth = round_to_nearest(np.random.uniform(0, 360))
    elevation = round_to_nearest(np.random.uniform(-90, 90))
    return (azimuth, elevation)


def random_light_source():
    a, e = random_direction()
    intensity = random.randint(1, 10)
    return a, e, intensity


def round_to_nearest(value, base=30):
    rounded = round(value / base) * base
    if rounded > 180:
        rounded -= 360
    elif rounded < -180:
        rounded += 360
    return rounded


def truncated_normal(a, b, mean=None, std_dev=None):
    if mean is None:
        mean = (a + b) / 2  # default mean at the center
    if std_dev is None:
        std_dev = (b - a) / 6  # 99.7% of values within [a, b]

    # convert to standard normal space
    lower, upper = (a - mean) / std_dev, (b - mean) / std_dev
    return truncnorm.rvs(lower, upper, loc=mean, scale=std_dev)


def random_time_limit(a, b, mean=None, std_dev=None):
    return round(truncated_normal(a, b, mean=mean, std_dev=std_dev))


def random_perspective_variation():
    return random.choices(["fish-eye lens", "two-point", "one-point", "three-point"], weights=[0.2, 0.35, 0.1, 0.35], k=1)[0]


def hsl_to_rgb(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h / 360, l, s)
    return tuple(int(c * 255) for c in (r, g, b))


def random_interval(min_val, max_val, spread=0.3):
    start = random.uniform(min_val, max_val - spread)
    end = min(start + random.uniform(spread * 0.5, spread), max_val)
    return (round(start, 2), round(end, 2))


def generate_random_sat_light_ranges():
    palette_type = random.choice(["vibrant", "muted", "dark", "light", "balanced"])
    
    if palette_type == "vibrant":
        sat_range = random_interval(0.7, 1.0)  # strong, saturated colors
        light_range = random_interval(0.4, 0.7)  # mid to bright
    elif palette_type == "muted":
        sat_range = random_interval(0.2, 0.6)  # lower saturation
        light_range = random_interval(0.4, 0.8)
    elif palette_type == "dark":
        sat_range = random_interval(0.4, 0.9)
        light_range = random_interval(0.2, 0.5)  # darker shades
    elif palette_type == "light":
        sat_range = random_interval(0.2, 0.7)
        light_range = random_interval(0.6, 0.9)  # light, pastel-like
    else:  # balanced
        sat_range = random_interval(0.4, 0.9)
        light_range = random_interval(0.3, 0.7)
    
    return sat_range, light_range, palette_type


def generate_palette(harmony="random", num_colors=3,
                     sat_range=None, light_range=None):

    available_harmonies = ["triadic", "complementary", "analogous", "golden"]
    
    if harmony == "random":
        harmony = random.choice(available_harmonies)
    
    if sat_range is None or light_range is None:
        sat_range, light_range, palette_type = generate_random_sat_light_ranges()
    
    palette = []
    
    # determine hues based on harmony rules.
    if harmony == "triadic":
        # Triadic: evenly spaced every 120° for 3 colors.
        base_hue = random.randint(0, 359)
        hues = [(base_hue + i * 120) % 360 for i in range(num_colors)]
    
    elif harmony == "complementary":
        # Complementary: two colors 180° apart.
        base_hue = random.randint(0, 359)
        hues = [base_hue, (base_hue + 180) % 360]
        if num_colors > 2:
            # If more than two colors are needed, add an analogous variant.
            hues.append((base_hue + 30) % 360)
            hues = hues[:num_colors]
    
    elif harmony == "analogous":
        # Analogous: pick a base and then use small hue offsets.
        base_hue = random.randint(0, 359)
        step = 30  # adjust as desired
        hues = [(base_hue + i * step) % 360 for i in range(num_colors)]
    
    elif harmony == "golden":
        # Golden ratio method to pick hues.
        golden_ratio_conjugate = 0.61803398875
        h = random.random()  # a value between 0 and 1
        hues = []
        for _ in range(num_colors):
            h = (h + golden_ratio_conjugate) % 1
            hues.append(int(h * 360))
    
    else:
        # Fallback: random hues.
        hues = [random.randint(0, 359) for _ in range(num_colors)]
    
    # Assign saturation and lightness to each color.
    for idx, hue in enumerate(hues):
        # optionally, differentiate the first color
        if idx == 0:
            # for example, make the first color a bit more neutral
            s = random.uniform(0.2, 0.5)
            l = random.uniform(0.5, 0.7)
        else:
            s = random.uniform(*sat_range)
            l = random.uniform(*light_range)
        palette.append((hue, s, l))
    
    return palette, harmony, palette_type


def generate_mean_std_from_paper_size(paper_size, a, b):
    match paper_size:
        case 'A3': alpha, beta = 5, 2
        case 'A5': alpha, beta = 2, 5
        case _: alpha, beta = 2, 2
    
    mean = alpha / (alpha + beta)
    var = (alpha * beta) / ((alpha + beta)**2 * (alpha + beta + 1))
    std_dev = np.sqrt(var)
    mean_scaled = a + mean * (b - a)
    std_dev_scaled = std_dev * (b - a)
    return mean_scaled, std_dev_scaled


def generate_mean_std_from_exercise_level(level, a, b):
    match level:
        case 'Level 1: Foundations': alpha, beta = 1, 6
        case 'Level 2 - Exploring Forms and Perspective': alpha, beta = 2, 5
        case 'Level 3: Combining and Manipulating Forms': alpha, beta = 2, 2
        case 'Level 4: Advanced Visualization': alpha, beta = 2, 2
        case 'Level 5 - Creative Exploration and Storytelling': alpha, beta = 5, 2
        case _: alpha, beta = 2, 2
    
    mean = alpha / (alpha + beta)
    var = (alpha * beta) / ((alpha + beta)**2 * (alpha + beta + 1))
    std_dev = np.sqrt(var)
    mean_scaled = a + mean * (b - a)
    std_dev_scaled = std_dev * (b - a)
    return mean_scaled, std_dev_scaled

"""
----------------------------------------------------
            PRINTING:
----------------------------------------------------
"""

def print_palette():
    palette, harmony, palette_type = generate_palette()
    print(f" > Color palette: ({harmony}, {palette_type}) ", end="")
    for h, s, l in palette:
        r, g, b = hsl_to_rgb(h, s, l)
        print(f"\033[48;2;{r};{g};{b}m  \033[0m", end="  ")
    print()


def print_last_bar():
    print('--------------------------------')


def print_random_perspective():
    a, e = random_direction()
    variation = random_perspective_variation()
    print(f" > Camera rotation: (azimuth {a}º, elevation {e}º)")
    print(f" > Perspective: {variation}")


def print_random_light_source():
    a, e, i = random_light_source()
    print(f" > Light source: (azimuth {a}º, elevation {e}º, intensity {i}/10)")


def print_random_traditional_medium():
    medium_1 = random_traditional_mediums()
    medium_2 = random_traditional_mediums()
    i = 50
    while medium_1 == medium_2 and i > 0:
        medium_2 = random_traditional_mediums()
        i -= 1
    print(f" > Medium: {medium_1} (optional: {medium_2})")


def print_random_category():
    category = random_category()
    print(f" > Category: {category}")


def print_random_restriction(prob=0.05):
    a = random.random()
    if random.random() < prob:
        print(f" > Restriction: {random_restriction()}")


def print_random_time_limit(a, b):
    print(f" > Time limit: {random_time_limit(a, b)} min")


def print_random_paper_size_and_time_limit(weights, a, b):
    paper_size = random_paper_size(weights=weights)
    mean, std_dev = generate_mean_std_from_paper_size(paper_size, a, b)
    print(f" > Paper size: {paper_size}")
    time_limit = random_time_limit(a, b, mean=mean, std_dev=std_dev)
    print(f" > Time limit: {time_limit} min")
    return time_limit



def print_bar_with_title(title):
    beginning = "\n---"
    n_left = 32 - len(beginning) - len(title)
    result = beginning + title + n_left * '-'
    print(result)


"""
----------------------------------------------------
            COMBINATIONS:
----------------------------------------------------
"""


def complete_anatomy_prompt():
    print_bar_with_title(" ANATOMY PROMPT ")
    print_random_perspective()
    print(f" > Sex: {random_sex()}")
    print(f" > Physique: {random_physique()}")
    print(f" > Anatomy: {random_lvl(random_anatomy)}")
    print_random_light_source()
    print_random_traditional_medium()
    print_palette()
    time_limit = print_random_paper_size_and_time_limit([0.5, 94.5, 5], 8, 88)
    print_last_bar()
    return time_limit


def complete_specific_anatomy_prompt():
    print_bar_with_title(" SPECIFIC ANATOMY PROMPT ")
    print_random_perspective()
    print(f" > Sex: {random_sex()}")
    print(f" > Physique: {random_physique()}")
    print(f" > Anatomy: {random_lvl(random_anatomy, levels=[5])}")
    print_random_light_source()
    print_random_traditional_medium()
    print_palette()
    time_limit = print_random_paper_size_and_time_limit([0.5, 94.5, 5], 8, 88)
    print_last_bar()
    return time_limit


def complete_anatomy_motion_prompt():
    print_bar_with_title(" ANATOMY MOTION PROMPT ")
    print_random_perspective()
    print(f" > Sex: {random_sex()}")
    print(f" > Physique: {random_physique()}")
    print(f" > Anatomy: {random_anatomy_motion()}")
    print_random_light_source()
    print_random_traditional_medium()
    print_palette()
    time_limit = print_random_paper_size_and_time_limit([0.5, 94.5, 5], 8, 88)
    print_last_bar()
    return time_limit


def complete_face_prompt():
    print_bar_with_title(" FACE PROMPT ")
    print_random_perspective()
    print(f" > Sex: {random_sex()}")
    print(f" > Physique: {random_physique()}")
    print_random_light_source()
    print(f" > Emotion: {random_lvl(random_emotion_to_body_expression, levels=[3,4])}")
    print_random_traditional_medium()
    print_palette()
    print_random_restriction(prob=0.08)
    time_limit = print_random_paper_size_and_time_limit([0.5, 93, 6.5], 8, 88)
    print_last_bar()
    return time_limit


def complete_face_part_prompt():
    print_bar_with_title(" FACE PART ")
    print_random_perspective()
    print(f" > Sex: {random_sex()}")
    print(f" > Physique: {random_physique()}")
    print(f" > Face part: {random_face_part()}")
    print_random_light_source()
    print(f" > Emotion: {random_lvl(random_emotion_to_body_expression, levels=[3,4])}")
    print_random_traditional_medium()
    print_palette()
    print_random_restriction(prob=0.08)
    time_limit = print_random_paper_size_and_time_limit([0.5, 90, 9.5], 2, 68)
    print_last_bar()
    return time_limit


def complete_hand_prompt():
    print_bar_with_title(" HANDS PROMPT ")
    print(f" > Sex: {random_sex()}")
    print(f" > Physique: {random_physique()}")
    print_random_light_source()
    print(f" > Emotion: {random_lvl(random_emotion_to_body_expression, levels=[3,4])}")
    print_random_traditional_medium()
    print_palette()
    print_random_restriction(prob=0.05)
    time_limit = print_random_paper_size_and_time_limit([0.5, 95, 4.5], 5, 50)
    print_last_bar()
    return time_limit


def complete_category_prompt():
    print_bar_with_title(" CATEGORY ")
    print_random_light_source()
    print_random_category()
    print_random_traditional_medium()
    print_palette()
    print_random_restriction(prob=0.03)
    time_limit = print_random_paper_size_and_time_limit([0.5, 94.5, 5], 10, 120)
    print_last_bar()
    return time_limit


def complete_feet_prompt():
    print_bar_with_title(" FEET PROMPT ")
    print(f" > Sex: {random_sex()}")
    print(f" > Physique: {random_physique()}")
    print_random_light_source()
    print(f" > Emotion: {random_lvl(random_emotion_to_body_expression, levels=[3,4])}")
    print_random_traditional_medium()
    print_palette()
    print_random_restriction(prob=0.05)
    time_limit = print_random_paper_size_and_time_limit([0.5, 95, 4.5], 5, 50)
    print_last_bar()
    return time_limit


def complete_exercise_prompt():
    print_bar_with_title(" EXERCISE PROMPT ")
    exercise = random_exercise()
    print(f" > Exercise: {exercise[:-1]}")
    print(f" :: {exercise[-1]}")
    print_random_traditional_medium()
    print_palette()
    time_limit = random_time_limit(5, 70)
    print(f" > Time limit: {time_limit} min")
    print_last_bar()
    return time_limit


def complete_daily_exercise_prompt():
    print_bar_with_title(" DAILY EXERCISE PROMPT ")
    exercise = random_daily_exercise([0.05, 0.11, 0.27, 0.29, 0.28])
    print(f" > Daily exercise: {exercise[0]}")
    print(f" :: {exercise[1]}")
    print_random_traditional_medium()
    print_palette()
    mean, std_dev = generate_mean_std_from_exercise_level(exercise[0], 2, 48)
    time_limit = random_time_limit(5, 50, mean=mean, std_dev=std_dev)
    print(f" > Time limit: {time_limit} min")
    print_last_bar()
    return time_limit


def random_complete_prompt():
    complete_prompt_functions = [
        complete_exercise_prompt, complete_daily_exercise_prompt, complete_face_prompt, complete_face_part_prompt, 
        complete_anatomy_prompt, complete_specific_anatomy_prompt, complete_anatomy_motion_prompt, 
        complete_hand_prompt, complete_feet_prompt, complete_category_prompt,
    ]
    random.choice(complete_prompt_functions)()


def complete_daily_plan():
    print('\n ============================================ ')
    print(' ==============-« DAILY PLAN »-============== ')
    print(' ============================================ \n')
    time_limits = []
    time_limits.append(random.choices([
        complete_exercise_prompt, complete_daily_exercise_prompt
    ], weights=[0.5, 0.5], k=1)[0]())
    print()
    time_limits.append(random.choices([
        complete_face_prompt,
        complete_face_part_prompt,
    ], weights=[0.5, 0.5], k=1)[0]())
    print()
    time_limits.append(random.choices([
        complete_anatomy_prompt, complete_specific_anatomy_prompt, complete_anatomy_motion_prompt,
    ], weights=[
        0.4, 0.3, 0.3
    ], k=1)[0]())
    print()
    time_limits.append(random.choices([
        complete_hand_prompt,
        complete_feet_prompt
    ], weights=[0.8, 0.2], k=1)[0]())
    print()
    time_limits.append(complete_category_prompt())
    print()

    total_time = 0
    for time_limit in time_limits:
        if isinstance(time_limit, tuple):
            total_time += time_limit[2]
        elif isinstance(time_limit, int):
            total_time += time_limit

    total_hours = total_time // 60
    rest = total_time % 60

    print(f"\n  Total time: {total_hours}h {rest}min")
    print(' ============================================ ')


"""
----------------------------------------------------
            TESTING:
----------------------------------------------------
"""


def test_11():
    for _ in range(10):
        random_complete_prompt()


if __name__ == "__main__":
    complete_daily_plan()
