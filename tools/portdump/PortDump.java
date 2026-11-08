import com.cburch.logisim.circuit.Circuit;
import com.cburch.logisim.circuit.WidthIncompatibilityData;
import com.cburch.logisim.comp.Component;
import com.cburch.logisim.comp.EndData;
import com.cburch.logisim.data.Bounds;
import com.cburch.logisim.data.Location;
import com.cburch.logisim.file.Loader;
import com.cburch.logisim.file.LogisimFile;
import com.cburch.logisim.instance.InstanceComponent;
import com.cburch.logisim.instance.Port;
import com.cburch.logisim.instance.StdAttr;
import java.io.File;
import java.util.*;

/**
 * Loads a .circ with Logisim's own loader and prints, as JSON, every
 * component's bounds and ports (exact location, bit width, direction,
 * tooltip) plus how many other things touch each port, and the locations
 * of any bit-width conflicts. Used by the generator to place wires exactly
 * and by the checker to find dangling ports.
 *
 * Usage: java -cp logisim.jar:. PortDump file.circ [circuit]
 */
public class PortDump {
  static String q(String s) {
    return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
  }

  public static void main(String[] args) throws Exception {
    System.setProperty("java.awt.headless", "true");
    com.cburch.logisim.Main.headless = true;
    LogisimFile file = new Loader(null).openLogisimFile(new File(args[0]));
    StringBuilder out = new StringBuilder("{");
    boolean firstCirc = true;
    for (Circuit c : file.getCircuits()) {
      if (args.length > 1 && !c.getName().equals(args[1])) continue;
      if (!firstCirc) out.append(",");
      firstCirc = false;
      out.append("\n").append(q(c.getName())).append(":{\"comps\":[");
      boolean firstComp = true;
      for (Component comp : c.getNonWires()) {
        if (!firstComp) out.append(",");
        firstComp = false;
        String label = "";
        try {
          Object l = comp.getAttributeSet().getValue(StdAttr.LABEL);
          if (l != null) label = l.toString();
        } catch (Exception e) { }
        Bounds b = comp.getBounds();
        List<Port> ports = null;
        if (comp instanceof InstanceComponent ic) ports = ic.getInstance().getPorts();
        out.append("\n {\"name\":").append(q(comp.getFactory().getName()))
            .append(",\"loc\":[").append(comp.getLocation().getX()).append(",")
            .append(comp.getLocation().getY()).append("]")
            .append(",\"label\":").append(q(label))
            .append(",\"bounds\":[").append(b.getX()).append(",").append(b.getY()).append(",")
            .append(b.getWidth()).append(",").append(b.getHeight()).append("],\"ports\":[");
        int i = 0;
        for (EndData e : comp.getEnds()) {
          Location p = e.getLocation();
          int touch = 0;
          for (Component o : c.getNonWires(p)) if (o != comp) touch++;
          touch += c.getWires(p).size();
          String dir = e.isInput() && e.isOutput() ? "io" : e.isInput() ? "in" : "out";
          String tip = "";
          if (ports != null && i < ports.size() && ports.get(i).getToolTip() != null)
            tip = ports.get(i).getToolTip();
          if (i > 0) out.append(",");
          out.append("{\"x\":").append(p.getX()).append(",\"y\":").append(p.getY())
              .append(",\"w\":").append(e.getWidth().getWidth())
              .append(",\"dir\":").append(q(dir))
              .append(",\"tip\":").append(q(tip))
              .append(",\"touch\":").append(touch).append("}");
          i++;
        }
        out.append("]}");
      }
      out.append("],\"widthErrors\":[");
      Set<WidthIncompatibilityData> wid = c.getWidthIncompatibilityData();
      boolean firstW = true;
      if (wid != null) for (WidthIncompatibilityData w : wid) {
        if (!firstW) out.append(",");
        firstW = false;
        out.append("[").append(w.getPoint(0).getX()).append(",").append(w.getPoint(0).getY()).append("]");
      }
      out.append("]}");
    }
    out.append("\n}\n");
    System.out.print(out);
    System.out.flush();
    System.exit(0);
  }
}
