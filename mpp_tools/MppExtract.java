// ATLAS · ГПР-движок — извлечение задач/связей/критпути из .mpp через MPXJ.
// java -cp "<mpxj-jars>:." MppExtract <file1.mpp> [file2.mpp ...]
// stdout JSON: {"<basename>":{"tasks":[{id,wbs,level,cat,name,summary,days,start,finish,pct,crit,pred}],"meta":{...}}, ...}
import org.mpxj.*;
import org.mpxj.reader.UniversalProjectReader;
import java.util.*;
import java.io.File;

public class MppExtract {
  static String esc(String s){
    if(s==null) return "";
    StringBuilder b=new StringBuilder();
    for(char c: s.toCharArray()){
      switch(c){
        case '"': b.append("\\\""); break;
        case '\\': b.append("\\\\"); break;
        case '\n': b.append("\\n"); break;
        case '\r': break;
        case '\t': b.append(" "); break;
        default: b.append(c);
      }
    }
    return b.toString();
  }
  static String isoDate(Object d){
    if(d==null) return null;
    String s=String.valueOf(d);
    return s.length()>=10? s.substring(0,10): s;
  }
  static String extractOne(String path) throws Exception {
    ProjectFile prj = new UniversalProjectReader().read(path);
    ProjectProperties pp = prj.getProjectProperties();
    StringBuilder out=new StringBuilder();
    out.append("{\"tasks\":[");
    boolean first=true; String curCat=null;
    for(Task t: prj.getTasks()){
      if(t.getID()==null || t.getID()==0) continue;
      Integer lvl=t.getOutlineLevel();
      String name=t.getName();
      if(lvl!=null && lvl==3) curCat=name;
      Integer days=null; Duration dur=t.getDuration();
      if(dur!=null){ try{ days=(int)Math.round(dur.convertUnits(TimeUnit.DAYS,pp).getDuration()); }catch(Exception e){ days=(int)Math.round(dur.getDuration()); } }
      Number pn=t.getPercentageComplete();
      String pct = pn==null? "null" : String.valueOf(Math.round(pn.doubleValue())/100.0);
      String start=isoDate(t.getStart()), finish=isoDate(t.getFinish());
      StringBuilder preds=new StringBuilder("[");
      List<Relation> rels=t.getPredecessors();
      if(rels!=null){ boolean pf=true;
        for(Relation r: rels){ Task p=r.getPredecessorTask();
          if(p==null||p.getID()==null) continue;
          if(!pf) preds.append(","); pf=false; preds.append(p.getID()); } }
      preds.append("]");
      if(!first) out.append(","); first=false;
      out.append("{")
        .append("\"id\":").append(t.getID()).append(",")
        .append("\"wbs\":\"").append(esc(t.getWBS())).append("\",")
        .append("\"level\":").append(lvl==null?1:lvl).append(",")
        .append("\"cat\":").append(curCat==null?"null":("\""+esc(curCat)+"\"")).append(",")
        .append("\"name\":\"").append(esc(name)).append("\",")
        .append("\"summary\":").append(t.getSummary()?"true":"false").append(",")
        .append("\"days\":").append(days==null?"null":days).append(",")
        .append("\"start\":").append(start==null?"null":("\""+start+"\"")).append(",")
        .append("\"finish\":").append(finish==null?"null":("\""+finish+"\"")).append(",")
        .append("\"pct\":").append(pct).append(",")
        .append("\"crit\":").append(t.getCritical()?"true":"false").append(",")
        .append("\"pred\":").append(preds).append("}");
    }
    out.append("],\"meta\":{")
       .append("\"start\":").append(isoDate(pp.getStartDate())==null?"null":("\""+isoDate(pp.getStartDate())+"\"")).append(",")
       .append("\"finish\":").append(isoDate(pp.getFinishDate())==null?"null":("\""+isoDate(pp.getFinishDate())+"\"")).append(",")
       .append("\"name\":\"").append(esc(pp.getProjectTitle())).append("\"")
       .append("}}");
    return out.toString();
  }
  public static void main(String[] a) throws Exception {
    StringBuilder out=new StringBuilder("{"); boolean first=true;
    for(String path: a){
      String base=new File(path).getName();
      String inner;
      try{ inner=extractOne(path); }
      catch(Exception e){ inner="{\"error\":\""+esc(e.toString())+"\"}"; }
      if(!first) out.append(","); first=false;
      out.append("\"").append(esc(base)).append("\":").append(inner);
    }
    out.append("}");
    System.out.println(out.toString());
  }
}
