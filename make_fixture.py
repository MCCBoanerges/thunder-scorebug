#!/usr/bin/env python3
"""Build a test fixture that mirrors the real mccthunder.com homepage markup.

The data below was read out of the live DOM (composite calendar) on 2026-09-14 so the parser can be
exercised without network access. Regenerate if the site's markup changes.
"""
import json

EVENTS = [
    dict(day="FRIDAY", month="SEP", date="11", site="AT", sport="WOMENS CROSS COUNTRY",
         opponent="BUTLER COMMUNITY COLLEGE", city="EL DORADO, KAN.", result="", time="9:00 AM",
         logo="/themes/mccthunder2020/images/teams/butler.png", link=""),
    dict(day="FRIDAY", month="SEP", date="11", site="AT", sport="MENS CROSS COUNTRY",
         opponent="BUTLER COMMUNITY COLLEGE", city="EL DORADO, KAN.", result="", time="9:45 AM",
         logo="/themes/mccthunder2020/images/teams/butler.png", link=""),
    dict(day="FRIDAY", month="SEP", date="11", site="VS.", sport="WOMENS VOLLEYBALL",
         opponent="FAITH BAPTIST BIBLE COLLEGE", city="MANHATTAN, KAN.", result="W, 3-0", time="",
         logo="/themes/mccthunder2020/images/teams/faithb.png", link=""),
    dict(day="FRIDAY", month="SEP", date="11", site="AT", sport="MENS SOCCER",
         opponent="EMMAUS UNIVERSITY", city="DUBUQUE, IOWA", result="W, 5-4", time="",
         logo="/themes/mccthunder2020/images/teams/emmaus.png", link=""),
    dict(day="SATURDAY", month="SEP", date="12", site="AT", sport="MENS SOCCER",
         opponent="FAITH BAPTIST BIBLE COLLEGE", city="ANKENY, IOWA", result="L, 0-5", time="",
         logo="/themes/mccthunder2020/images/teams/faithb.png", link=""),
    dict(day="MONDAY", month="SEP", date="14", site="AT", sport="WOMENS GOLF",
         opponent="COTTEY COLLEGE", city="NEVADA, MO.", result="", time="9:00 AM",
         logo="/themes/mccthunder2020/images/teams/cottey.png", link=""),
    dict(day="TUESDAY", month="SEP", date="15", site="AT", sport="WOMENS GOLF",
         opponent="COTTEY COLLEGE", city="NEVADA, MO.", result="", time="9:00 AM",
         logo="/themes/mccthunder2020/images/teams/cottey.png", link=""),
    dict(day="TUESDAY", month="SEP", date="15", site="AT", sport="MENS SOCCER",
         opponent="KANSAS CHRISTIAN COLLEGE", city="OVERLAND PARK, KAN.", result="", time="1:00 PM",
         logo="/themes/mccthunder2020/images/teams/kanscc.png", link=""),
    dict(day="TUESDAY", month="SEP", date="15", site="VS.", sport="WOMENS VOLLEYBALL",
         opponent="CENTRAL BIBLE UNIVERSITY", city="MANHATTAN, KAN.", result="", time="6:00 PM",
         logo="/themes/mccthunder2020/images/teams/cbusai.png", link=""),
    dict(day="FRIDAY", month="SEP", date="18", site="VS.", sport="WOMENS VOLLEYBALL",
         opponent="STERLING COLLEGE", city="MANHATTAN, KAN.", result="", time="6:00 PM",
         logo="/themes/mccthunder2020/images/teams/sterlc.png", link=""),
    dict(day="FRIDAY", month="SEP", date="18", site="AT", sport="MENS CROSS COUNTRY, WOMENS CROSS COUNTRY",
         opponent="STERLING COLLEGE", city="STERLING, KAN.", result="", time="6:15 PM",
         logo="/themes/mccthunder2020/images/teams/sterlc.png", link=""),
    dict(day="SATURDAY", month="SEP", date="19", site="VS.", sport="WOMENS VOLLEYBALL",
         opponent="OZARK CHRISTIAN COLLEGE", city="MANHATTAN, KAN.", result="", time="1:00 PM",
         logo="/themes/mccthunder2020/images/teams/ozarkc.png", link=""),
    dict(day="SATURDAY", month="SEP", date="19", site="VS.", sport="MENS SOCCER",
         opponent="OZARK CHRISTIAN COLLEGE", city="MANHATTAN, KAN.", result="", time="3:30 PM",
         logo="/themes/mccthunder2020/images/teams/ozarkc.png", link=""),
]

ROW = """    <div class="views-row">
      <div class="views-field views-field-field-date-3"><div class="field-content">
        <span class="day">{day}</span><span class="month">{month}</span><span class="date">{date}</span>
      </div></div>
      <div class="views-field views-field-nothing-1"><span class="field-content">
        <div class="logo"><img src="{logo}" alt=""></div>
        <div class="site">{site}</div>
        <div class="event">
          <div class="sport">{sport}</div>
          <div class="opponent">{opponent}</div>
          <div class="city">{city}</div>
        </div>
        <div class="details">
          <div class="result">{result}</div>
          <div class="live"></div>
          <div class="live-video">{video}</div>
          <div class="time">{time}</div>
        </div>
      </span></div>
    </div>"""


def main():
    rows = []
    for ev in EVENTS:
        video = (
            f'<a href="{ev["link"]}" target="_blank">Watch</a>' if ev["link"] else ""
        )
        rows.append(ROW.format(video=video, **ev))

    page = (
        "<!DOCTYPE html>\n<html><head><title>MCC Thunder</title></head><body>\n"
        '<div class="block-event-schedule view view-event-schedule view-id-event_schedule">\n'
        '  <div class="view-content">\n' + "\n".join(rows) + "\n  </div>\n</div>\n"
        "</body></html>\n"
    )
    with open("fixture.html", "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote fixture.html ({len(page)} bytes, {len(EVENTS)} rows)")


if __name__ == "__main__":
    main()
