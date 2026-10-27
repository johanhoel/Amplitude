import runpy, datetime as dt
ns = runpy.run_path(str(__import__("pathlib").Path(__file__).with_name("test_webui.py")))
c, root = ns["c"], ns["root"]
day = dt.date.today().isoformat()
c.post(f"/clip/{day}/camera1_100000/label", data={"name": "Alex", "crop": "camera1_100000_faces/unknown_1.jpg", "add_to_library": "1"})
j = c.get(f"/api/clip/{day}/camera1_100000").get_json()
# test_webui tagged this face "Sam"; re-tagging it as Alex moves the tag and the library photo to Alex
tags, tag = [t["name"] for t in j["tags"]], j["faces"][0]["tag"]
sam = (root / "photos" / "Sam" / "camera1_100000_unknown_1.jpg").exists()
alex = (root / "photos" / "Alex" / "camera1_100000_unknown_1.jpg").exists()
good = tags == ["Alex"] and tag == "Alex" and not sam and alex
print(f"{'PASS' if good else 'FAIL'}  re-tag Sam -> Alex: tags {tags}, face tag {tag}, Sam keeps the crop {sam}, Alex has it {alex}")
